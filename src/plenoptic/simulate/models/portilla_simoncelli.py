import torch
import einops
from torch import Tensor
import torch.fft
import torch.nn as nn
from ..canonical_computations.steerable_pyramid_freq import SteerablePyramidFreq
import numpy as np
from collections import OrderedDict
import matplotlib.pyplot as plt
import matplotlib as mpl
from ...tools.display import clean_up_axes, update_stem, clean_stem_plot
from ...tools.data import to_numpy
from ...tools import stats, signal
from ...tools.validate import validate_input
from typing import Tuple, List, Literal, Union, Optional, Dict

SCALES_TYPE = Union[
    int, Literal["pixel_statistics", "residual_lowpass", "residual_highpass"]
]


class PortillaSimoncelli(nn.Module):
    r"""Portila-Simoncelli texture statistics.

    The Portilla-Simoncelli (PS) texture statistics are a set of image
    statistics, first described in [1]_, that are proposed as a sufficient set
    of measurements for describing visual textures. That is, if two texture
    images have the same values for all PS texture stats, humans should
    consider them as belonging to the same family of texture.

    The PS stats are computed based on the steerable pyramid [2]_. They consist
    of the local auto-correlations, cross-scale (within-orientation)
    correlations, and cross-orientation (within-scale) correlations of both the
    pyramid coefficients and the local energy (as computed by those
    coefficients). Additionally, they include the first four global moments
    (mean, variance, skew, and kurtosis) of the image and down-sampled versions
    of that image. See the paper and notebook for more description.

    Parameters
    ----------
    image_shape:
        Shape of input image.
    n_scales:
        The number of pyramid scales used to measure the statistics (default=4)
    n_orientations:
        The number of orientations used to measure the statistics (default=4)
    spatial_corr_width:
        The width of the spatial cross- and auto-correlation statistics in the representation
    use_true_correlations:
        In the original Portilla-Simoncelli model the statistics in the representation
        that are labelled correlations were actually covariance matrices (i.e. not properly
        scaled).  In order to match the original statistics use_true_correlations must be
        set to false. But in order to synthesize metamers from this model use_true_correlations
        must be set to True (note that, in this case, the diagonal entries are
        not rescaled, i.e., they're the covariances).

    Attributes
    ----------
    pyr: SteerablePyramidFreq
        The complex steerable pyramid object used to calculate the portilla-simoncelli representation
    pyr_coeffs: OrderedDict
        The coefficients of the complex steerable pyramid.
    mag_pyr_coeffs: OrderedDict
        The magnitude of the pyramid coefficients.
    real_pyr_coeffs: OrderedDict
        The real parts of the pyramid coefficients.
    scales: list
        The names of the unique scales of coefficients in the pyramid.
    representation_scales: list
        The scale for each coefficient in its vector form
    representation: dictionary
        A dictionary containing the Portilla-Simoncelli statistics

    References
    ----------
    .. [1] J Portilla and E P Simoncelli. A Parametric Texture Model based on
       Joint Statistics of Complex Wavelet Coefficients. Int'l Journal of
       Computer Vision. 40(1):49-71, October, 2000.
       http://www.cns.nyu.edu/~eero/ABSTRACTS/portilla99-abstract.html
       http://www.cns.nyu.edu/~lcv/texture/
    .. [2] E P Simoncelli and W T Freeman, "The Steerable Pyramid: A Flexible
       Architecture for Multi-Scale Derivative Computation," Second Int'l Conf
       on Image Processing, Washington, DC, Oct 1995.

    """

    def __init__(
        self,
        image_shape: Tuple[int, int],
        n_scales: int = 4,
        n_orientations: int = 4,
        spatial_corr_width: int = 9,
        use_true_correlations: bool = True,
    ):
        super().__init__()

        self.image_shape = image_shape
        self.spatial_corr_width = spatial_corr_width
        self.n_scales = n_scales
        self.n_orientations = n_orientations
        self.pyr = SteerablePyramidFreq(
            self.image_shape,
            height=self.n_scales,
            order=self.n_orientations - 1,
            is_complex=True,
            tight_frame=False,
            downsample=False,
        )

        self.use_true_correlations = use_true_correlations
        self.scales = (
            ["pixel_statistics", "residual_lowpass"]
            + [ii for ii in range(n_scales - 1, -1, -1)]
            + ["residual_highpass"]
        )
        self.representation_scales = self._get_representation_scales()

    def _get_representation_scales(self) -> List[SCALES_TYPE]:
        r"""Get the vector indicating the scale of each statistic, for coarse-to-fine synthesis.

        The vector is composed of the following values: 'pixel_statistics',
        'residual_lowpass', 'residual_highpass' and integer values from 0 to
        self.n_scales-1. It is the same size as the representation vector
        returned by this object's forward method.

        """
        # There are 6 pixel statistics by default
        pixel_statistics = ["pixel_statistics"] * 6

        # These (`scales` and `scales_with_lowpass`) are the basic building
        # blocks of the scale assignments for many of the statistics calculated
        # by the PortillaSimoncelli model.
        scales = [s for s in range(self.n_scales)]
        scales_with_lowpass = scales + ["residual_lowpass"]
        # this repeats the first element of scales n_orientations times, then
        # the second, etc. e.g., [0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, ...]
        scales_by_ori = [s for s in scales for _ in range(self.n_orientations)]

        # magnitude_means
        magnitude_means = ["residual_highpass"] + scales_by_ori + ["residual_lowpass"]

        # skew_reconstructed
        skew_reconstructed = scales_with_lowpass

        # kurtosis_reconstructed
        kurtosis_reconstructed = scales_with_lowpass

        # variance_reconstructed
        std_reconstructed = scales_with_lowpass

        auto_corr = self.spatial_corr_width**2 * scales_with_lowpass
        auto_corr_mag = self.spatial_corr_width**2 * scales_by_ori

        cross_orientation_corr_mag = self.n_orientations**2 * scales_with_lowpass
        ori_crossed = max(2 * self.n_orientations, 5)
        cross_orientation_corr_real = ori_crossed**2 * scales_with_lowpass

        cross_scale_corr_mag = self.n_orientations**2 * scales
        cross_scale_corr_real = (2 * self.n_orientations * ori_crossed) * scales
        var_highpass_residual = ["residual_highpass"]

        if self.use_true_correlations:
            scales = (
                pixel_statistics
                + magnitude_means
                + auto_corr_mag
                + skew_reconstructed
                + kurtosis_reconstructed
                + auto_corr
                # if we're using true correlations, want to include the std of
                # the reconstructed images (this is implicitly included in the
                # unscaled correlations if use_true_correlations=False)
                + std_reconstructed
                + cross_orientation_corr_mag
                + cross_scale_corr_mag
                + cross_orientation_corr_real
                + cross_scale_corr_real
                + var_highpass_residual
            )
        else:
            scales = (
                pixel_statistics
                + magnitude_means
                + auto_corr_mag
                + skew_reconstructed
                + kurtosis_reconstructed
                + auto_corr
                + cross_orientation_corr_mag
                + cross_scale_corr_mag
                + cross_orientation_corr_real
                + cross_scale_corr_real
                + var_highpass_residual
            )

        return scales

    def forward(
        self, image: Tensor, scales: Optional[List[SCALES_TYPE]] = None
    ) -> Tensor:
        r"""Generate Texture Statistics representation of an image.

        Note that separate batches and channels are analyzed in parallel.

        Parameters
        ----------
        image :
            A 4d tensor (batch, channel, height, width) containing the image(s) to
            analyze.
        scales :
            Which scales to include in the returned representation. If None, we
            include all scales. Otherwise, can contain subset of values present
            in this model's ``scales`` attribute, and the returned vector will
            then contain the subset of the full representation corresponding to
            those scales.

        Returns
        -------
        representation_vector:
            3d tensor of shape (B,C,S) containing the measured texture
            statistics.

        """
        validate_input(image)

        # pyr_coeffs is a 6d tensor of shape (batch, channel, scales,
        # orientations, height, width) containing the complex-valued oriented
        # bands, while highpass and lowpass are real-valued 4d tensors of shape
        # (batch, channel, height, width). The lowpass tensor has been demeaned
        # (independently for each batch and channel)
        pyr_coeffs, pyr_info, highpass, lowpass = self._compute_pyr_coeffs(image)

        ### SECTION 1 (STATISTIC: pixel_statistics) ##################
        #  Calculate pixel statistics (mean, variance, skew, kurtosis, min, max).
        pixel_stats = self._compute_pixel_stats(image)

        ### SECTION 2 (STATISTIC: mean_magnitude) ####################
        # Calculate the mean of the magnitude of each band of pyramid
        # coefficients.  Additionally, this section creates two
        # other dictionaries of coefficients: magnitude_pyr_coeffs
        # and real_pyr_coeffs, which contain the demeaned magnitude of the
        # pyramid coefficients and the real part of the pyramid
        # coefficients respectively.

        # calculate two intermediate representations:
        #   1) demeaned magnitude of the pyramid coefficients,
        #   2) real part of the pyramid coefficients
        # and the means of the pyramid coefficient magnitudes, which is part of
        # the texture representation.
        mag_means, mag_pyr_coeffs, real_pyr_coeffs = self._compute_intermediate_representations(pyr_coeffs)
        mag_mean_rescale = torch.repeat_interleave(torch.arange(self.n_scales), self.n_orientations)
        mag_means = mag_means * torch.pow(2, mag_mean_rescale)
        mag_means = einops.pack([highpass.abs().mean((-2, -1)), mag_means,
                                 lowpass.abs().mean((-2, -1)) * torch.pow(2, 1+mag_mean_rescale[-1])],
                                'b c *')[0]

        ### SECTION 3 (STATISTICS: auto_correlation_magnitude,
        #                          skew_reconstructed,
        #                          kurtosis_reconstructed,
        #                          auto_correlation_reconstructed) #####
        #
        # Calculates:
        # 1) the central auto-correlation of the magnitude of each
        # orientation/scale band.
        #
        # 2) the central auto-correlation of the low-pass residuals
        # for each scale of the pyramid (auto_correlation_reconstructed),
        # where the residual at each scale is reconstructed from the
        # previous scale.  (Note: the lowpass residual of the pyramid
        # is low-pass filtered before this reconstruction process begins,
        # see below).
        #
        # 3) the skew and the kurtosis of the reconstructed
        # low-pass residuals (skew_reconstructed, kurtosis_reconstructed).
        # The skew and kurtosis are calculated with the auto-correlation
        # statistics because like #2 (above) they rely on the reconstructed
        # low-pass residuals, making it more efficient (in terms of memory
        # and/or compute time) to calculate it at the same time.

        # tensor of shape (batch, channel, n_scales+1, height, width)
        reconstructed_images = self._reconstruct_lowpass_at_each_scale(
            real_pyr_coeffs,
            pyr_info,
            highpass,
            lowpass
        )

        # tensor of shape: (batch, channel, spatial_corr_width,
        # spatial_corr_width, n_scales, n_orientations)
        autocorr_mags, _ = self._compute_autocorr(mag_pyr_coeffs)

        # autocorr_recon is a tensor of shape (batch, channel,
        # spatial_corr_width, spatial_corr_width, n_scales+1), and var_recon is
        # a tensor of shape (batch, channel, n_scales+1)
        autocorr_recon, var_recon = self._compute_autocorr(reconstructed_images)
        skew_recon, kurtosis_recon = self._compute_skew_kurtosis_recon(reconstructed_images, var_recon, pixel_stats[..., 1])
        # in order to match the original implementation (done on down-sampled
        # images), need to scale these up (skew and kurtosis are fine).
        var_recon = var_recon * torch.pow(4, torch.arange(0, 2*var_recon.shape[-1], 2))
        # std_recon, skew_recon, and kurtosis_recon will all end up as shape
        # (batch, channel, n_scales+1)
        if self.use_true_correlations:
            std_recon = var_recon**0.5
        else:
            std_recon = torch.empty((0))


        ### SECTION 4 (STATISTICS: cross_orientation_correlation_magnitude,
        #                          cross_scale_correlation_magnitude,
        #                          cross_orientation_correlation_real,
        #                          cross_scale_correlation_real) ###########
        # Calculates cross-orientation and cross-scale correlations for the
        # real parts and the magnitude of the pyramid coefficients.
        #

        # this will be a tensor of shape (batch, channel, n_orientations,
        # n_orientations, n_scales)
        cross_ori_corr_mags = self._compute_cross_correlation(mag_pyr_coeffs, mag_pyr_coeffs)
        # ... and then we add an extra scale along the final dimension (it's
        # full of 0s)
        cross_ori_corr_mags = torch.cat([cross_ori_corr_mags, torch.zeros_like(cross_ori_corr_mags[..., -1:])], -1)

        # this will be a tensor of shape (batch, channel, n_orientations,
        # n_orientations, n_scales)
        cross_ori_corr_real = self._compute_cross_correlation(real_pyr_coeffs, real_pyr_coeffs)
        # need to concatenate the cross correlations on the shifted upsampled
        # lowpass for ... some reason. and add some extra zeros as well. this
        # brings the final shape up to (batch, channel, max(2*n_orientations,
        # 5), max(2*n_orientations, 5), n_scales+1)
        cross_ori_corr_real = self._concat_lowpass_to_cross_ori_real(cross_ori_corr_real,
                                                                     lowpass)

        if self.n_scales != 1:
            # double the phase the coefficients, so we can correctly compute
            # correlations across scales.
            phase_doubled_mags, phase_doubled_sep = self._double_phase_pyr_coeffs(pyr_coeffs)
            # in order to match the original implementation (done on down-sampled
            # images), need to rescale these
            phase_double_rescale = torch.pow(2., torch.arange(-1, self.n_scales-2))
            phase_double_rescale = phase_double_rescale.view(1, 1, self.n_scales-1, 1, 1, 1)
            phase_doubled_mags = phase_doubled_mags * phase_double_rescale
            phase_doubled_sep = phase_doubled_sep * phase_double_rescale
            # this will be a tensor of shape (batch, channel, n_orientations,
            # n_orientations, n_scales-1).
            cross_scale_corr_mags = self._compute_cross_correlation(mag_pyr_coeffs[:, :, :-1], phase_doubled_mags)
            # ... and then we add an extra scale along the final dimension (it's
            # full of 0s)
            cross_scale_corr_mags = torch.cat([cross_scale_corr_mags, torch.zeros_like(cross_scale_corr_mags[..., -1:])], -1)
            # this will be a tensor of shape (batch, channel, n_orientations,
            # 2*n_orientations, n_scales-1)
            cross_scale_corr_real = self._compute_cross_correlation(real_pyr_coeffs[:, :, :-1], phase_doubled_sep)
        else:
            # in this case, we just have these zeros at the end
            cross_scale_corr_mags = torch.zeros_like(cross_ori_corr_mags[..., :1])
            cross_scale_corr_real = torch.empty((0))

        # need to concatenate the cross correlations on the shifted upsampled
        # lowpass for ... some reason. and concatenate some zeros. this brings
        # the final shape up to (batch, channel, 2*n_orientations,
        # max(2*n_orientations, 5), n_scales)
        cross_scale_corr_real = self._concat_lowpass_to_cross_scale_real(cross_scale_corr_real, lowpass,
                                                                         real_pyr_coeffs[:,:,-1])

        # SECTION 5: the variance of the high-pass residual, of shape (batch, channel)
        var_highpass_residual = highpass.pow(2).mean(dim=(-2, -1))

        all_stats = [pixel_stats, mag_means, autocorr_mags, skew_recon,
                     kurtosis_recon, autocorr_recon]
        if self.use_true_correlations:
            all_stats += [std_recon]
        all_stats += [cross_ori_corr_mags, cross_scale_corr_mags,
                      cross_ori_corr_real, cross_scale_corr_real, var_highpass_residual]
        representation_vector = einops.pack(all_stats, 'b c *')[0]

        if scales is not None:
            representation_vector = self.remove_scales(representation_vector, scales)

        # this is about ~2x slower than the non-downsampled version from the
        # previous commit and differs more from the previous versions.
        return representation_vector

    def remove_scales(
            self, representation_vector: Tensor, scales_to_keep: List[SCALES_TYPE]
    ) -> Tensor:
        """Remove statistics not associated with scales

        For a given representation_vector and a list of scales_to_keep, this
        attribute removes all statistics *not* associated with those scales.

        Note that calling this method will always remove statistics.

        Parameters
        ----------
        representation_vector:
            3d tensor containing the measured representation statistics.
        scales_to_keep:
            Which scales to include in the returned representation. Can contain
            subset of values present in this model's ``scales`` attribute, and
            the returned vector will then contain the subset of the full
            representation corresponding to those scales.

        Returns
        ------
        limited_representation_vector :
            Representation vector with some statistics removed.

        """
        ind = torch.tensor(
            [i for i, s in enumerate(self.representation_scales) if s in scales_to_keep]
        ).to(representation_vector.device)
        return representation_vector.index_select(-1, ind)

    def convert_to_vector(self, stats_dict: OrderedDict) -> Tensor:
        r"""Converts dictionary of statistics to a vector.

        While the dictionary representation is easier to manually inspect, the
        vector representation is required by plenoptic's synthesis objects.

        Parameters
        ----------
        stats_dict :
             Dictionary of representation.

        Returns
        -------
        3d vector of statistics.

        See also
        --------
        convert_to_dict:
            Convert vector representation to dictionary.

        """
        list_of_stats = []
        for val in stats_dict.values():
            if isinstance(val, OrderedDict):
                # these are all 2d
                list_of_stats.append(torch.stack([vv for vv in val.values()], dim=-1))
            else:
                if val.ndim == 2:
                    list_of_stats.append(val.unsqueeze(-1))
                else:
                    list_of_stats.append(val.flatten(start_dim=2, end_dim=-1))
        return torch.cat(list_of_stats, dim=-1)

    def convert_to_dict(self, vec: Tensor) -> OrderedDict:
        """Converts vector of statistics to a dictionary.

        While the vector representation is required by plenoptic's synthesis
        objects, the dictionary representation is easier to manually inspect.

        Parameters
        ----------
        vec
            3d vector of statistics.

        Returns
        -------
        Dictionary of representation, with informative keys.

        See also
        --------
        convert_to_vector:
            Convert dictionary representation to vector.

        """
        if vec.shape[-1] != len(self.representation_scales):
            raise ValueError(
                "representation vector is the wrong length (expected "
                f"{len(self.representation_scales)} but got {vec.shape[-1]})!"
                " Did you remove some of the scales? (i.e., by setting "
                "scales in the forward pass)? convert_to_dict does not "
                "support such vectors."
            )
        rep = OrderedDict()
        rep["pixel_statistics"] = OrderedDict()
        rep["pixel_statistics"]["mean"] = vec[..., 0]
        rep["pixel_statistics"]["var"] = vec[..., 1]
        rep["pixel_statistics"]["skew"] = vec[..., 2]
        rep["pixel_statistics"]["kurtosis"] = vec[..., 3]
        rep["pixel_statistics"]["min"] = vec[..., 4]
        rep["pixel_statistics"]["max"] = vec[..., 5]

        n_filled = 6

        # magnitude_means
        rep["magnitude_means"] = OrderedDict()
        keys = ['residual_highpass'] + [(sc, ori) for sc in range(self.n_scales) for ori in range(self.n_orientations)] + ['residual_lowpass']
        for ii, k in enumerate(keys):
            rep["magnitude_means"][k] = vec[..., n_filled + ii]
        n_filled += ii + 1

        # auto_correlation_magnitude
        nn = (
            self.spatial_corr_width,
            self.spatial_corr_width,
            self.n_scales,
            self.n_orientations,
        )
        rep["auto_correlation_magnitude"] = vec[
            ..., n_filled : (n_filled + np.prod(nn))
        ].unflatten(-1, nn)
        n_filled += np.prod(nn)

        # skew_reconstructed & kurtosis_reconstructed
        nn = self.n_scales + 1
        rep["skew_reconstructed"] = vec[..., n_filled : (n_filled + nn)]
        n_filled += nn

        rep["kurtosis_reconstructed"] = vec[..., n_filled : (n_filled + nn)]
        n_filled += nn

        # auto_correlation_reconstructed
        nn = (self.spatial_corr_width, self.spatial_corr_width, (self.n_scales + 1))
        rep["auto_correlation_reconstructed"] = vec[
            ..., n_filled : (n_filled + np.prod(nn))
        ].unflatten(-1, nn)
        n_filled += np.prod(nn)

        if self.use_true_correlations:
            nn = self.n_scales + 1
            rep["std_reconstructed"] = vec[..., n_filled : (n_filled + nn)]
            n_filled += nn

        # cross_orientation_correlation_magnitude
        nn = (self.n_orientations, self.n_orientations, (self.n_scales + 1))
        rep["cross_orientation_correlation_magnitude"] = vec[
            ..., n_filled : (n_filled + np.prod(nn))
        ].unflatten(-1, nn)
        n_filled += np.prod(nn)

        # cross_scale_correlation_magnitude
        nn = (self.n_orientations, self.n_orientations, self.n_scales)
        rep["cross_scale_correlation_magnitude"] = vec[
            ..., n_filled : (n_filled + np.prod(nn))
        ].unflatten(-1, nn)
        n_filled += np.prod(nn)

        # cross_orientation_correlation_real
        nn = (
            max(2 * self.n_orientations, 5),
            max(2 * self.n_orientations, 5),
            (self.n_scales + 1),
        )
        rep["cross_orientation_correlation_real"] = vec[
            ..., n_filled : (n_filled + np.prod(nn))
        ].unflatten(-1, nn)
        n_filled += np.prod(nn)

        # cross_scale_correlation_real
        nn = (2 * self.n_orientations, max(2 * self.n_orientations, 5), self.n_scales)
        rep["cross_scale_correlation_real"] = vec[
            ..., n_filled : (n_filled + np.prod(nn))
        ].unflatten(-1, nn)
        n_filled += np.prod(nn)

        # var_highpass_residual
        rep["var_highpass_residual"] = vec[..., n_filled]

        return rep

    def _compute_pyr_coeffs(self, image: Tensor) -> Tuple[Tensor, Tuple, Tensor, Tensor]:
        """Compute pyramid coefficients of image.

        Parameters
        ----------
        image :
            4d tensor of shape (batch, channel, height, width) containing the
            image

        Returns
        -------
        pyr_coeffs :
            6d tensor of shape (batch, channel, scales, orientations, height,
            width) containing the complex-valued oriented bands
        pyr_info :
            Tuple containing the info necessary to reconstruct the pyramid
            dictionary.
        highpass :
            The residual highpass as a real-valued 4d tensor (batch, channel,
            height, width)
        lowpass :
            The residual lowpass as a real-valued 4d tensor (batch, channel,
            height, width). This tensor has been demeaned as well
            (independently for each batch and channel).

        """
        pyr_coeffs = self.pyr.forward(image)
        # separate out the residuals and demean the residual lowpass
        lowpass = pyr_coeffs.pop('residual_lowpass')
        lowpass = lowpass - lowpass.mean(dim=(-2, -1), keepdim=True)
        highpass = pyr_coeffs.pop('residual_highpass')

        # convert the oriented bands into a tensor and arrange them like
        # (batch, channel, scale, orientation, height, width)
        pyr_coeffs, pyr_info = self.pyr.convert_pyr_to_tensor(pyr_coeffs, split_complex=False)
        pyr_coeffs = einops.rearrange(pyr_coeffs, 'b (c s o) h w -> b c s o h w', s=self.n_scales, o=self.n_orientations)
        return pyr_coeffs, pyr_info, highpass, lowpass

    @staticmethod
    def _compute_pixel_stats(image: Tensor) -> Tensor:
        """Compute the pixel stats: first four moments, min, and max.

        Parameters
        ----------
        image :
            4d tensor of shape (batch, channel, height, width) containing input
            image. Stats are computed indepently for each batch and channel.

        Returns
        -------
        pixel_stats :
            3d tensor of shape (batch, channel, 6) containing the mean,
            variance, skew, kurtosis, minimum pixel value, and maximum pixel
            value (in that order)

        """
        mean = torch.mean(image, dim=(-2, -1), keepdim=True)
        var = torch.var(image, dim=(-2, -1))
        skew = stats.skew(image, mean=mean, var=var, dim=[-2, -1])
        kurtosis = stats.kurtosis(image, mean=mean, var=var, dim=[-2, -1])
        # can't compute min/max over two dims simultaneously with
        # torch.min/max, so use einops
        img_min = einops.reduce(image, 'b c h w -> b c', 'min')
        img_max = einops.reduce(image, 'b c h w -> b c', 'max')
        # mean needed to be unflattened to be used by skew and kurtosis
        # correctly, but we'll want it to be flattened like this in the final
        # representation vector
        return einops.pack([mean, var, skew, kurtosis, img_min, img_max], 'b c *')[0]

    def _compute_intermediate_representations(self, pyr_coeffs: Tensor) -> Tuple[Tensor, Tensor, Tensor]:
        """Compute useful intermediate representations.

        These representations are:
          1) demeaned magnitude of the pyramid coefficients,
          2) real part of the pyramid coefficients
          3) the means of the pyramid coefficient magnitudes (this one is part
             of the texture representation)

        The first two are used in computing some of the texture representation.

        Parameters
        ----------
        pyr_coeffs :
            Complex steerable pyramid coefficients (without residuals), as
            tensor of shape (batch, channel, n_scales, n_orientations, height,
            width)

        Returns
        -------
        magnitude_means :
           Tensor of shape (batch, channel, n_scales * n_orientations + 2)
           containing the mean of each steerable coefficient band's magnitude.
        magnitude_pyr_coeffs :
           Tensor of shape (batch, channel, n_scales, n_orientations, height,
           width) (same as ``pyr_coeffs``), containing the demeaned magnitude
           of the steerable pyramid coefficients (i.e., pyr_coeffs.abs() -
           pyr_coeffs.abs().mean((-2, -1)))
        real_pyr_coeffs :
           Tensor of shape (batch, channel, n_scales, n_orientations, height,
           width) (same as ``pyr_coeffs``), containing the real components
           of the steerable pyramid coefficients (i.e., pyr_coeffs.real)

        """
        magnitude_pyr_coeffs = pyr_coeffs.abs()
        real_pyr_coeffs = pyr_coeffs.real
        magnitude_means = magnitude_pyr_coeffs.mean((-2, -1), keepdim=True)
        magnitude_pyr_coeffs = magnitude_pyr_coeffs - magnitude_means
        magnitude_means = magnitude_means.flatten(2)
        return magnitude_means, magnitude_pyr_coeffs, real_pyr_coeffs

    def _reconstruct_lowpass_at_each_scale(self, real_pyr_coeffs: Tensor, pyr_info: Tuple, highpass: Tensor, lowpass: Tensor) -> Tensor:
        """Reconstruct the lowpass unoriented image at each scale.

        The autocorrelation, skew, and kurtosis of each of these images is part
        of the texture representation.

        Parameters
        ----------
        real_pyr_coeffs :
            6d tensor of shape (batch, channel, scales, orientations, height,
            width) containing the real components of the oriented bands
        pyr_info :
            Tuple containing the info necessary to reconstruct the pyramid
            dictionary.
        highpass :
            The residual highpass as a real-valued 4d tensor (batch, channel,
            height, width)
        lowpass :
            The residual lowpass as a real-valued 4d tensor (batch, channel,
            height, width).

        Returns
        -------
        reconstructed_images :
            5d tensor of shape (batch, channel, n_scales+1, height, width)
            containing the reconstructed unoriented image at each scale, from
            fine to coarse. The final image is reconstructed just from the
            residual lowpass image.
        """
        # recon_pyr requires a dictionary of the sort we get from pyr(info) so
        # we reconstruct the tensor (with just the real components) and
        # reconstruct it using convert_tensor_to_pyr
        real_pyr_coeffs = einops.pack([highpass, real_pyr_coeffs, lowpass], 'b * h w')[0]
        pyr_keys = ['residual_highpass'] + list(pyr_info[-1]) + ['residual_lowpass']
        pyr_dict = self.pyr.convert_tensor_to_pyr(real_pyr_coeffs, *pyr_info[:2], pyr_keys)

        reconstructed_images = [self.pyr.recon_pyr(pyr_dict, levels=['residual_lowpass'])]
        # go through scales backwards
        for lev in range(self.n_scales-1, -1, -1):
            recon = self.pyr.recon_pyr(pyr_dict, levels=lev)
            reconstructed_images.append(recon + reconstructed_images[-1])
        return einops.pack(reconstructed_images[::-1], 'b c * h w')[0]

    def _compute_autocorr(self, coeffs_tensor: Tensor) -> Tuple[Tensor, Tensor]:
        """Compute the autocorrelation of some statistics.

        Parameters
        ----------
        coeffs_tensor :
            Tensor of shape (batch, channel, *, height, width), where * is one
            or two additional dimensions. Intended use case:
            magnitude_pyr_coeffs (which is 6d, with * containing n_scales,
            n_orientations) or reconstructed_images (which is 5d, with *
            containing n_scales+1)

        Returns
        -------
        autocorrs :
            Tensor of shape (batch, channel, spatial_corr_width,
            spatial_corr_width, *) containing the autocorrelation of each of
            the first four dimensions of ``coeffs_tensor`` over the
            ``spatial_corr_width``.
        vars :
            Tensor of shape (batch, channel, *) containing the variance
            computed independently over each of the first four dimensions of
            ``coeffs_tensor``

        """
        if coeffs_tensor.ndim == 6:
            dims = 's o'
        elif coeffs_tensor.ndim == 5:
            dims = 's'
        else:
            raise ValueError("coeffs_tensor must have 5 or 6 dimensions!")
        acs = signal.autocorrelation(coeffs_tensor)
        # this central value is the variance
        var = signal.center_crop(acs, 1)
        if self.use_true_correlations:
            acs = acs / var
        var = einops.rearrange(var, f'b c {dims} h w -> b c ({dims} h w)')

        def shrink_and_crop(x, i):
            # downsample all scales but the first, to match original
            # implementation (where autocorrelation is computed on the
            # progressively-downsampled scales)
            if i != 0:
                x = signal.shrink(x, 2**i)
            return signal.center_crop(x, self.spatial_corr_width)

        # having a for loop is not ideal (slower on gpu) but I don't think it's
        # possible to convert something that's vmapped over to an int
        # (https://github.com/google/jax/discussions/8973?sort=top) or have
        # dynamic shapes in vmap
        # (https://jax.readthedocs.io/en/latest/notebooks/Common_Gotchas_in_JAX.html#dynamic-shapes)
        acs = torch.stack([shrink_and_crop(acs[:,:,i], i)
                           for i in range(acs.shape[2])], 2)
        return einops.rearrange(acs, f'b c {dims} a1 a2 -> b c a1 a2 {dims}'), var

    def _compute_skew_kurtosis_recon(self, reconstructed_images: Tensor, var_recon: Tensor,
                                     img_var: Tensor) -> Tuple[Tensor, Tensor]:
        """Computes the skew and kurtosis of each lowpass reconstructed image.

        For each scale, if the ratio of its variance to the pixel variance of
        the original image are below a threshold of 1e-6, skew and kurtosis are
        assigned default values of 0 or 3, respectively.

        Parameters
        ----------
        reconstructed_images :
            5d tensor of shape (batch, channel, n_scales+1, height, width)
            containing the reconstructed unoriented image at each scale, from
            fine to coarse. The final image is reconstructed just from the
            residual lowpass image.
        var_recon :
            Tensor of shape (batch, channel, n_scales+1) containing the
            variance of each tensor in reconstruced_images
        img_var :
            Tensor of shape (batch, channel) containing the pixel variance
            (from pixel_stats tensor)

        Returns
        -------
        skew_recon, kurtosis_recon :
            Tensors of shape (batch, channel, n_scales+1) containing the skew
            and kurtosis, respectively, of each tensor in
            ``reconstructed_images``.

        """
        skew_recon = stats.skew(reconstructed_images, mean=0,
                                var=var_recon, dim=[-2, -1])
        kurtosis_recon = stats.kurtosis(reconstructed_images, mean=0,
                                        var=var_recon, dim=[-2, -1])
        skew_default = torch.zeros_like(skew_recon)
        kurtosis_default = 3 * torch.ones_like(kurtosis_recon)
        # if this variance ratio is too small, then use the default values
        # instead
        unstable_locs = var_recon / img_var > 1e-6
        skew_recon = torch.where(unstable_locs, skew_recon, skew_default)
        kurtosis_recon = torch.where(unstable_locs, kurtosis_recon, kurtosis_default)
        return skew_recon, kurtosis_recon

    def _compute_cross_correlation(self, coeffs_tensor: Tensor, coeffs_tensor_other: Tensor) -> Tensor:
        """Compute cross-correlations.

        Parameters
        ----------
        coeffs_tensor, coeffs_tensor_other :
            The two 6d tensors of shape (batch, channel, scales, n_orientations,
            height, width) to be correlated.


        Returns
        -------
        cross_ori_corr :
            Tensor of shape (batch, channel, n_orientations, n_orientations,
            scales) containing the cross-orientation correlations at each
            scale.

        """
        cross_ori_corr = einops.einsum(coeffs_tensor, coeffs_tensor_other,
                                       'b c s o1 h w, b c s o2 h w -> b c s o1 o2')
        cross_ori_corr = cross_ori_corr / torch.mul(*coeffs_tensor.shape[-2:])
        if self.use_true_correlations:
            std = torch.std(coeffs_tensor, (-3, -2, -1), keepdim=True).squeeze(-1)
            std_other = torch.std(coeffs_tensor_other, (-3, -2, -1), keepdim=True).squeeze(-1)
            cross_ori_corr = cross_ori_corr / (std * std_other)
        return einops.rearrange(cross_ori_corr, f'b c s o1 o2 -> b c o1 o2 s')

    def _create_lowpass_corr_tensor(self, lowpass: Tensor) -> Tensor:
        """Upsample lowpass, flatten, and roll.

        At the highest scale, the cross-scale real correlations are between the
        coefficients at that scale and an upsampled, shifted version of the
        lowpass residuals. This constructs that tensor.

        """
        if self.n_scales == 1:
            downsampled_lowpass = lowpass
        else:
            downsampled_lowpass = signal.shrink(lowpass, 2**(self.n_scales-1))
        downsampled_lowpass = downsampled_lowpass * 2**(self.n_scales-2)
        downsampled_lowpass = downsampled_lowpass.transpose(-2, -1)
        return torch.stack(
            (
                downsampled_lowpass.flatten(2),
                downsampled_lowpass.roll(1, -2).flatten(2),
                downsampled_lowpass.roll(-1, -2).flatten(2),
                downsampled_lowpass.roll(1, -1).flatten(2),
                downsampled_lowpass.roll(-1, -1).flatten(2),
            ),
            -1,
        )
    
    def _concat_lowpass_to_cross_ori_real(self, cross_ori_corr_real: Tensor, lowpass: Tensor) -> Tensor:
        """Tricky little bit.

        For some reason, the original code concatenates the correlations of the
        upsampled, shifted residual lowpass to the cross orientation
        correlation real. this makes it a very weird shape, and is also unclear
        as to why it's useful. but that's what we do here.

        """
        lowpass_num_el = torch.mul(*lowpass.shape[-2:])
        upsampled_lowpass = self._create_lowpass_corr_tensor(lowpass)
        upsampled_lowpass_corr = self.compute_crosscorrelation(upsampled_lowpass,
                                                               upsampled_lowpass,
                                                               lowpass_num_el)
        # ... and a whole bunch of dummy zeros, to bring the final shape up to
        # (batch, channel, max(2*n_orientations, 5), max(2*n_orientations, 5), n_scales+1)
        dim = max(2 * self.n_orientations, 5)
        cross_ori_corr_real = nn.functional.pad(cross_ori_corr_real, (0, 0, 0, dim-self.n_orientations, 0, dim-self.n_orientations), 'constant', 0)
        upsampled_lowpass_corr = nn.functional.pad(upsampled_lowpass_corr, (0, dim-5, 0, dim-5), 'constant', 0)
        return torch.cat([cross_ori_corr_real, upsampled_lowpass_corr.unsqueeze(-1)], -1)

    def _double_phase_pyr_coeffs(self, pyr_coeffs: Tensor) -> Tuple[Tensor, Tensor]:
        """Upsample and double the phase of pyramid coefficients.

        Parameters
        ----------
        pyr_coeffs :
            Complex steerable pyramid coefficients (without residuals), as
            tensor of shape (batch, channel, n_scales, n_orientations, height,
            width)

        Returns
        -------
        doubled_phase_mags :
            The demeaned magnitude (i.e., pyr_coeffs.abs()) of each upsampled
            double-phased coefficient. Has the same shape as the input.
        doubled_phase_separate :
            The real and imaginary parts of each double-phased coefficient. Has
            shape (batch, channel, n_scales, 2*n_orientations, height, width),
            with the real component found at the same orientation index as the
            input, and the imaginary at orientation+self.n_orientations.

        """
        # don't do this for the finest scale
        doubled_phase = signal.modulate_phase(pyr_coeffs[:, :, 1:], 2)
        doubled_phase_mags = doubled_phase.abs()
        doubled_phase_mags = doubled_phase_mags - doubled_phase_mags.mean((-2, -1), keepdim=True)
        ## this minus here SHOULD BE REMOVED, it's just because they computed the
        ## negative real component by accident
        doubled_phase_separate = einops.pack([-doubled_phase.real, doubled_phase.imag],
                                             'b c s * h w')[0]
        return doubled_phase_mags, doubled_phase_separate

    def _concat_lowpass_to_cross_scale_real(self, cross_scale_corr_real: Tensor, lowpass: Tensor,
                                            real_pyr_coeffs_last_scale: Tensor) -> Tensor:
        """Tricky little bit.

        For some reason, the original code concatenates the correlations
        between the upsampled, shifted residual lowpass and the coarsest scale.
        to the cross scale correlation real. this makes it a very weird shape,
        and is also unclear as to why it's useful. but that's what we do here.

        """
        if self.n_scales != 1:
            real_pyr_coeffs_last_scale = signal.shrink(real_pyr_coeffs_last_scale,
                                                       2**(self.n_scales-1))
            real_pyr_coeffs_last_scale = real_pyr_coeffs_last_scale * 2**(self.n_scales-1)
        band_num_el = torch.mul(*real_pyr_coeffs_last_scale.shape[-2:])
        orientation_bands = einops.rearrange(real_pyr_coeffs_last_scale,
                                             'b c o h w -> b c (w h) o')
        upsampled_lowpass = self._create_lowpass_corr_tensor(lowpass)
        upsampled_lowpass_corr = self.compute_crosscorrelation(orientation_bands,
                                                               upsampled_lowpass,
                                                               band_num_el)
        # ... and a whole bunch of dummy zeros, to bring the final shape up to
        # (batch, channel, 2*n_orientations, max(2*n_orientations, 5), n_scales)
        dim = max(2 * self.n_orientations, 5)
        if cross_scale_corr_real.numel() != 0:
            # in this case, n_scales==1, so this is empty
            cross_scale_corr_real = nn.functional.pad(cross_scale_corr_real, (0, 0, 0, dim-2*self.n_orientations, 0, 2*self.n_orientations-self.n_orientations), 'constant', 0)
        upsampled_lowpass_corr = nn.functional.pad(upsampled_lowpass_corr, (0, dim-5, 0, 2*self.n_orientations-self.n_orientations), 'constant', 0)
        return torch.cat([cross_scale_corr_real, upsampled_lowpass_corr.unsqueeze(-1)], -1)

    def compute_crosscorrelation(self, ch1, ch2, band_num_el):
        r"""Computes either the covariance of the two matrices or the cross-correlation
        depending on the value self.use_true_correlations.

        Parameters
        ----------
        ch1: torch.Tensor
            First matrix for cross correlation.
        ch2: torch.Tensor
            Second matrix for cross correlation.
        band_num_el: int
            Number of elements for bands in the scale

        Returns
        -------
        torch.Tensor
            cross-correlation.

        """

        if self.use_true_correlations:
            return ch1.transpose(-2, -1) @ ch2 / (band_num_el * ch1.std() * ch2.std())
        else:
            return ch1.transpose(-2, -1) @ ch2 / (band_num_el)

    def plot_representation(
            self,
            data: Union[Tensor, OrderedDict],
            ax: Optional[mpl.axes.Axes] = None,
            figsize: Tuple[float, float] = (15, 15),
            ylim: Optional[Tuple[float, float]] = None,
            batch_idx: int = 0,
            title: Optional[str] = None,
    ) -> Tuple[mpl.figure.Figure, List[mpl.axes.Axes]]:

        r"""Plot the representation in a human viewable format -- stem
        plots with data separated out by statistic type.


        Parameters
        ----------
        data :
            The data to show on the plot. Else, should look like the output of
            ``self.forward(img)``, with the exact same structure (e.g., as
            returned by ``metamer.representation_error()`` or another instance
            of this class).
        ax :
            Axes where we will plot the data. If an ``mpl.axes.Axes``, will
            subdivide into 9 new axes. If None, we create a new figure.
        figsize :
            The size of the figure. Ignored if ax is not None.
        ylim :
            The ylimits of the plot.
        batch_idx :
            Which index to take from the batch dimension (the first one)
        title : string
            Title for the plot

        Returns
        -------
        fig:
            Figure containing the plot
        axes:
            List of 9 axes containing the plot

        """

        n_rows = 3
        n_cols = 3

        rep = self.convert_to_dict(data)
        data = self._representation_for_plotting(rep)

        # Set up grid spec
        if ax is None:
            # we add 2 to order because we're adding one to get the
            # number of orientations and then another one to add an
            # extra column for the mean luminance plot
            fig = plt.figure(figsize=figsize)
            gs = mpl.gridspec.GridSpec(n_rows, n_cols, fig)
        else:
            # warnings.warn("ax is not None, so we're ignoring figsize...")
            # want to make sure the axis we're taking over is basically invisible.
            ax = clean_up_axes(
                ax, False, ["top", "right", "bottom", "left"], ["x", "y"]
            )
            gs = ax.get_subplotspec().subgridspec(n_rows, n_cols)
            fig = ax.figure

        # plot data
        axes = []

        for i, (k, v) in enumerate(data.items()):

            ax = fig.add_subplot(gs[i // 3, i % 3])
            if isinstance(v, OrderedDict):
                # need to make sure these are not tensors when we call the
                # plotting function
                ax = clean_stem_plot(
                    [to_numpy(v_) for v_ in v.values()], ax, k, ylim=ylim
                )
            else:
                ax = clean_stem_plot(to_numpy(v).flatten(), ax, k, ylim=ylim)

            axes.append(ax)

        return fig, axes

    def _representation_for_plotting(
            self, rep: OrderedDict, batch_idx: int = 0
    ) -> OrderedDict:
        r"""Converts the data into a dictionary representation that is more convenient for plotting.

        Intended as a helper function for plot_representation.

        """
        data = OrderedDict()
        data["pixels+var_highpass"] = rep["pixel_statistics"]
        data["pixels+var_highpass"]["var_highpass_residual"] = rep[
            "var_highpass_residual"
        ]
        if self.use_true_correlations:
            data["var+skew+kurtosis"] = torch.stack(
                (
                    rep["std_reconstructed"],
                    rep["skew_reconstructed"],
                    rep["kurtosis_reconstructed"],
                )
            )
        else:
            data["skew+kurtosis"] = torch.stack(
                (rep["skew_reconstructed"], rep["kurtosis_reconstructed"])
            )

        for (k, v) in rep.items():
            if k not in [
                    "pixel_statistics",
                    "var_highpass_residual",
                    "kurtosis_reconstructed",
                    "skew_reconstructed",
                    "std_reconstructed",
            ]:

                if not isinstance(v, dict) and v.squeeze().dim() >= 3:
                    vals = OrderedDict()
                    for ss in range(v.shape[2]):
                        tmp = torch.norm(v[:, :, ss, ...], p=2, dim=[0, 1])
                        if len(tmp.shape) == 0:
                            tmp = tmp.unsqueeze(0)
                            vals[ss] = tmp
                            dk = torch.cat(list(vals.values()))
                            data[k] = dk

                else:
                    data[k] = v

        return data

    def update_plot(
            self,
            axes: List[mpl.axes.Axes],
            data: Optional[Union[Tensor, OrderedDict]] = None,
            batch_idx: int = 0,
    ) -> List[mpl.artist.Artist]:
        r"""Update the information in our representation plot

        This is used for creating an animation of the representation
        over time. In order to create the animation, we need to know how
        to update the matplotlib Artists, and this provides a simple way
        of doing that. It relies on the fact that we've used
        ``plot_representation`` to create the plots we want to update
        and so know that they're stem plots.

        We take the axes containing the representation information (note
        that this is probably a subset of the total number of axes in
        the figure, if we're showing other information, as done by
        ``Metamer.animate``), grab the representation from plotting and,
        since these are both lists, iterate through them, updating as we
        go.

        We can optionally accept a data argument, in which case it
        should look just like the representation of this model.

        In order for this to be used by ``FuncAnimation``, we need to
        return Artists, so we return a list of the relevant artists, the
        ``markerline`` and ``stemlines`` from the ``StemContainer``.

        Parameters
        ----------
        axes :
            A list of axes to update. We assume that these are the axes
            created by ``plot_representation`` and so contain stem plots
            in the correct order.
        batch_idx :
            Which index to take from the batch dimension (the first one)
        data :
            The data to show on the plot. Else, should look like the output of
            ``self.forward(img)``, with the exact same structure (e.g., as
            returned by ``metamer.representation_error()`` or another instance
            of this class).

        Returns
        -------
        stem_artists :
            A list of the artists used to update the information on the
            stem plots

        """
        stem_artists = []
        axes = [ax for ax in axes if len(ax.containers) == 1]
        data = self.convert_to_dict(data)
        rep = self._representation_for_plotting(data)
        for ax, d in zip(axes, rep.values()):
            if isinstance(d, dict):
                vals = np.array([dd.detach() for dd in d.values()])
            else:
                vals = d.flatten().detach().numpy()

            sc = update_stem(ax.containers[0], vals)
            stem_artists.extend([sc.markerline, sc.stemlines])
        return stem_artists

    def to(self, *args, **kwargs):
        r"""Moves and/or casts the parameters and buffers.

        This can be called as

        .. function:: to(device=None, dtype=None, non_blocking=False)

        .. function:: to(dtype, non_blocking=False)

        .. function:: to(tensor, non_blocking=False)

        Its signature is similar to :meth:`torch.Tensor.to`, but only accepts
        floating point desired :attr:`dtype` s. In addition, this method will
        only cast the floating point parameters and buffers to :attr:`dtype`
        (if given). The integral parameters and buffers will be moved
        :attr:`device`, if that is given, but with dtypes unchanged. When
        :attr:`non_blocking` is set, it tries to convert/move asynchronously
        with respect to the host if possible, e.g., moving CPU Tensors with
        pinned memory to CUDA devices.

        See below for examples.

        .. note::
            This method modifies the module in-place.
        Args:
            device (:class:`torch.device`): the desired device of the parameters
                and buffers in this module
            dtype (:class:`torch.dtype`): the desired floating point type of
                the floating point parameters and buffers in this module
            tensor (torch.Tensor): Tensor whose dtype and device are the desired
                dtype and device for all parameters and buffers in this module

        Returns:
            Module: self
        """
        self.pyr = self.pyr.to(*args, **kwargs)
        return self
