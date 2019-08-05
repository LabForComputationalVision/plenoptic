"""functions to perform spatial pooling, as seen in Freeman and Simoncelli, 2011

"""
import math
import torch
import warnings
from torch import nn
import numpy as np
import pyrtools as pt
import matplotlib.pyplot as plt


def calc_angular_window_width(n_windows):
    r"""calculate and return the window width for the angular windows

    this is the :math:`w_{\theta }` term in equation 10 of the paper's
    online methods

    Parameters
    ----------
    n_windows : `float`
        The number of windows to pack into 2 pi. Note that we don't
        require it to be an integer here, but the code that makes use of
        this does.

    Returns
    -------
    window_width : `float`
        The width of the polar angle windows.

    """
    return (2*np.pi) / n_windows


def calc_angular_n_windows(window_width):
    r"""calculate and return the number of angular windows

    this is the :math:`N_{\theta }` term in equation 10 of the paper's
    online method, which we've rearranged in order to get this.

    Parameters
    ----------
    window_width : `float`
        The width of the polar angle windows.

    Returns
    -------
    n_windows : `float`
        The number of windows that fit into 2 pi.

    """
    return (2*np.pi) / window_width


def calc_eccentricity_window_width(min_ecc=.5, max_ecc=15, n_windows=None, scaling=None):
    r"""calculate and return the window width for the eccentricity windows

    this is the :math:`w_e` term in equation 11 of the paper's online
    methods, which we also refer to as the radial width. Note that we
    take exactly one of ``n_windows`` or ``scaling`` in order to
    determine this value.

    Parameters
    ----------
    min_ecc : `float`, optional
        The minimum eccentricity, the eccentricity below which we do not
        compute pooling windows (in degrees). Parameter :math:`e_0` in
        equation 11 of the online methods.
    max_ecc : `float`, optional
        The maximum eccentricity, the outer radius of the image (in
        degrees). Parameter :math:`e_r` in equation 11 of the online
        methods.
    n_windows : `float` or `None`
        The number of log-eccentricity windows we create. ``n_windows``
        xor ``scaling`` must be set.
    scaling : `float` or `None`.
        The ratio of the eccentricity window's radial full-width at
        half-maximum to eccentricity (see the ``calc_scaling``
        function). ``n_windows`` xor ``scaling`` must be set.

    Returns
    -------
    window_width : `float`
        The width of the log-eccentricity windows.

    Notes
    -----
    No equation was given in the paper to calculate the window width,
    :math:`w_e` from the scaling, :math:`s`, so we derived it
    ourselves. We start with the final equation for the scaling, given
    in the Notes for the ``calc_scaling`` function.

    .. math::

        s &= \exp(w_e)^{.5} -  \exp(w_e)^{-.5} \\
        s &= \frac{\exp(w_e)-1}{\sqrt{\exp(w_e)}} \\
        s^2 &= \frac{\exp(2w_e)-2\exp(w_e)+1}{\exp(w_e)} \\
        s^2 &= \exp(w_e)-2+\frac{1}{\exp(w_e)} \\
        s^2+2 &= e^{w_e}+e^{-w_e} \\
        s^2e^{w_e}+2e^{w_e}&=e^{2w_e}+1 \\
        e^{2w_e} - e^{w_e}(s^2+2) +1 &=0

    And then solve using the quadratic formula:

    .. math::

        e^{w_e} &= \frac{s^2+2\pm\sqrt{(s^2+2)^2-4}}{2} \\
        e^{w_e} &= \frac{s^2+2\pm\sqrt{s^4+4s^2}}{2} \\
        e^{w_e} &= \frac{s^2+2\pm s\sqrt{s^2+4}}{2} \\
        w_e &= \log\left(\frac{s^2+2\pm s\sqrt{s^2+4}}{2}\right)

    The window width is strictly positive, so we only return the
    positive quadratic root (the one with plus in the numerator).

    """
    if scaling is not None:
        return np.log((scaling**2+2+scaling * np.sqrt(scaling**2+4))/2)
    elif n_windows is not None:
        return (np.log(max_ecc) - np.log(min_ecc)) / n_windows
    else:
        raise Exception("Exactly one of n_windows or scaling must be set!")


def calc_eccentricity_n_windows(window_width, min_ecc=.5, max_ecc=15):
    r"""calculate and return the number of eccentricity windows

    this is the :math:`N_e` term in equation 11 of the paper's online
    method, which we've rearranged in order to get this.

    Parameters
    ----------
    window_width : `float`
        The width of the log-eccentricity windows.
    min_ecc : `float`, optional
        The minimum eccentricity, the eccentricity below which we do not
        compute pooling windows (in degrees). Parameter :math:`e_0` in
        equation 11 of the online methods.
    max_ecc : `float`, optional
        The maximum eccentricity, the outer radius of the image (in
        degrees). Parameter :math:`e_r` in equation 11 of the online
        methods.

    Returns
    -------
    n_windows : `float`
        The number of log-eccentricity windows we create.

    """
    return (np.log(max_ecc) - np.log(min_ecc)) / window_width


def calc_scaling(n_windows, min_ecc=.5, max_ecc=15):
    r"""calculate and return the scaling value, as reported in the paper

    Scaling is the ratio of the eccentricity window's radial full-width
    at half-maximum to eccentricity. For eccentricity, we use the
    window's "central eccentricity", the one where the input to the
    mother window (:math:`x` in equation 9 in the online methods) is 0.

    Parameters
    ----------
    n_windows : `float`
        The number of log-eccentricity windows we create.
    min_ecc : `float`, optional
        The minimum eccentricity, the eccentricity below which we do not
        compute pooling windows (in degrees). Parameter :math:`e_0` in
        equation 11 of the online methods.
    max_ecc : `float`, optional
        The maximum eccentricity, the outer radius of the image (in
        degrees). Parameter :math:`e_r` in equation 11 of the online
        methods.

    Returns
    -------
    scaling : `float`.
        The ratio of the eccentricity window's radial full-width at
        half-maximum to eccentricity

    Notes
    -----
    No equation for the scaling, :math:`s`, was included in the paper,
    so we derived this ourselves. To start, we note that the mother
    window equation (equation 9) reaches its half-max (.5) at
    :math:`x=\pm .5`, and that, as above, we treat :math:`x=0` as the
    central eccentricity of the window. Then we must solve for these,
    using the values given within the parentheses in equation 11 as the
    value for :math:`x`, and take their ratios.

    It turns out that this holds for all permissible values of
    ``transition_region_width`` (:math:`t` in the equations) (try
    playing around with some plots if you don't believe me).

    Full-width half-maximum, :math:`W`, the difference between the two
    values of :math:`e_h`:

    .. math::

        \pm.5 &= \frac{\log(e_h) - (log(e_0)+w_e(n+1))}{w_e} \\
        e_h &= e_0 \cdot \exp(w_e(\pm.5+n+1)) \\
        W &= e_0 (\exp(w_e(n+1.5)) - \exp(w_e(n+.5))

    Window's central eccentricity, :math:`e_c`:

    .. math::

        0 &= \frac{\log(e_c) -(log(e_0)+w_e(n+1))}{w_e} \\
        e_c &= e_0 \cdot \exp(w_e(n+1))

    Then the scaling, :math:`s` is the ratio :math:`\frac{W}{e_c}`:

    .. math::

        s &= \frac{e_0 (\exp(w_e(n+1.5)) -  \exp(w_e(n+.5)))}{e_0 \cdot \exp(w_e(n+1))} \\
        s &= \frac{\exp(w_e(n+1.5))}{\exp(w_e(n+1))} -  \frac{\exp(w_e(n+.5))}{\exp(w_e(n+1))} \\
        s &= \exp(w_e(n+1.5-n-1)) -  \exp(w_e(n+.5-n-1)) \\
        s &= \exp(.5\cdot w_e) -  \exp(-.5\cdot w_e)

    Note that we don't actually use the value returned by
    ``calc_windows_central_eccentricity`` for :math:`e_c`; we simplify
    it away in the calculation above.

    """
    window_width = (np.log(max_ecc) - np.log(min_ecc)) / n_windows
    return np.exp(.5*window_width) - np.exp(-.5*window_width)


def calc_windows_central_eccentricity(n_windows, window_width, min_ecc=.5):
    r"""calculate the central eccentricity of each window

    These are the values :math:`e_c`, as referred to in ``calc_scaling``
    (for each of the n windows)

    Parameters
    ----------
    n_windows : `float`
        The number of log-eccentricity windows we create. n_windows can
        be a non-integer, in which case we round it up (thus one of our
        central eccentricities might be above the maximum eccentricity
        for the windows actually created)
    window_width : `float`
        The width of the log-eccentricity windows.
    min_ecc : `float`, optional
        The minimum eccentricity, the eccentricity below which we do not
        compute pooling windows (in degrees). Parameter :math:`e_0` in
        equation 11 of the online methods.

    Returns
    -------
    central_eccentricity : list
        A list of length ``n_windows``, with each entry giving
        :math:`e_c`, as below.

    Notes
    -----
    To find this value, we solve for the eccentricity where :math:`x=0`
    in equation 9:

    .. math::

        0 &= \frac{\log(e_c) -(log(e_0)+w_e(n+1))}{w_e} \\
        e_c &= e_0 \cdot \exp(w_e(n+1))

    """
    return [min_ecc * np.exp(window_width * (i+1)) for i in np.arange(np.ceil(n_windows))]


def calc_window_widths_actual(angular_window_width, radial_window_width, min_ecc=.5, max_ecc=15,
                              transition_region_width=.5):
    r"""calculate and return the actual widths of the windows, in angular and radial directions

    whereas ``calc_angular_window_width`` returns a term used in the
    equations to generate the windows, this returns the actual angular
    and radial widths of each set of windows (in degrees).

    We return four total widths, two by two for radial and angular by
    'top' and 'full'. By 'top', we mean the width of the flat-top region
    of each window (where the windows value is 1), and by 'full', we
    mean the width of the entire window

    Parameters
    ----------
    angular_window_width : float
        The width of the windows in the angular direction, as returned
        by ``calc_angular_window_width``
    radial_window_width : float
        The width of the windows in the radial direction, as returned by
        ``calc_eccentricity_window_width``
    min_ecc : `float`, optional
        The minimum eccentricity, the eccentricity below which we do not
        compute pooling windows (in degrees). Parameter :math:`e_0` in
        equation 11 of the online methods.
    max_ecc : `float`, optional
        The maximum eccentricity, the outer radius of the image (in
        degrees). Parameter :math:`e_r` in equation 11 of the online
        methods.
    transition_region_width : `float`, optional
        The width of the transition region, parameter :math:`t` in
        equation 9 from the online methods.

    Returns
    -------
    radial_top_width : list
        The width of the flat-top region of the windows in the radial
        direction (each value corresponds to a different ring of
        windows, from the fovea to the periphery).
    radial_full_width : list
        The full width of the windows in the radial direction (each
        value corresponds to a different ring of windows, from the fovea
        to the periphery).
    angular_top_width : list
        The width of the flat-top region of the windows in the angular
        direction (each value corresponds to a different ring of
        windows, from the fovea to the periphery).
    angular_full_width : list
        The full width of the windows in the angular direction (each
        value corresponds to a different ring of windows, from the fovea
        to the periphery).

    Notes
    -----
    In order to calculate the width in the angular direction, we start
    with the angular window width (:math:`w_{\theta }`). The 'top' width
    is then :math:`w_{\theta}(1-t)` and the 'full' width is
    :math:`w_{\theta}(1+t)`, where :math:`t` is the
    ``transition_region_width``. This gives us the width in radians, so
    we convert it to degrees by finding the windows' central
    eccentricity (:math:`e_c`, as referred to in ``calc_scaling`` and
    returned by ``calc_windows_central_eccentricity``), and find the
    circumference (in degrees) of the circle that goes through that
    eccentricity. We then multiply our width in radians by
    :math:`\frac{2\pi e_c}{2\pi}=e_c`.

    Calculating the width in the radial direction is slightly more
    complicated, because they're not symmetric or constant across the
    visual field. We start by noting, based on equation 9 in the paper,
    that the flat-top region is the region between :math:`x=\frac{\pm
    (1-t)}{2}` and the whole window is the region between
    :math:`x=\frac{\pm (1+t)}{2}`. We can then do a little bit of
    rearranging to forms used in this function.

    """
    n_radial_windows = np.ceil(calc_eccentricity_n_windows(radial_window_width, min_ecc, max_ecc))
    window_central_eccentricities = calc_windows_central_eccentricity(n_radial_windows,
                                                                      radial_window_width, min_ecc)
    radial_top_width = [min_ecc*(np.exp((radial_window_width*(3+2*i-transition_region_width))/2) -
                                 np.exp((radial_window_width*(1+2*i+transition_region_width))/2))
                        for i in np.arange(n_radial_windows)]
    radial_full_width = [min_ecc*(np.exp((radial_window_width*(3+2*i+transition_region_width))/2) -
                                  np.exp((radial_window_width*(1+2*i-transition_region_width))/2))
                         for i in np.arange(n_radial_windows)]
    angular_top_width = [angular_window_width * (1-transition_region_width) * e_c for e_c in
                         window_central_eccentricities]
    angular_full_width = [angular_window_width * (1+transition_region_width) * e_c for e_c in
                          window_central_eccentricities]
    return radial_top_width, radial_full_width, angular_top_width, angular_full_width


def mother_window(x, transition_region_width=.5):
    r"""Raised cosine 'mother' window function

    Used to give the weighting in each direction for the spatial pooling
    performed during the construction of visual metamers

    Notes
    -----
    For ``x`` values outside the function's domain, we return ``np.nan``
    (not 0)

    Equation 9 from the online methods of [1]_.

    Parameters
    ----------
    x : `float` or `array_like`
        The distance in a direction
    transition_region_width : `float`, optional
        The width of the transition region, parameter :math:`t` in
        equation 9 from the online methods. Must lie between 0 and 1.

    Returns
    -------
    `float`
        The value of the window at each value of ``x``.

    References
    ----------
    .. [1] Freeman, J., & Simoncelli, E. P. (2011). Metamers of the ventral stream. Nature
       Neuroscience, 14(9), 1195–1201. http://dx.doi.org/10.1038/nn.2889

    """
    if transition_region_width > 1 or transition_region_width < 0:
        raise Exception("transition_region_width must lie between 0 and 1!")
    if hasattr(x, '__iter__'):
        return np.array([mother_window(i, transition_region_width) for i in x])
    if -(1 + transition_region_width) / 2 < x <= (transition_region_width - 1) / 2:
        return np.cos(np.pi/2 * ((x - (transition_region_width-1)/2) / transition_region_width))**2
    elif (transition_region_width - 1) / 2 < x <= (1 - transition_region_width) / 2:
        return 1
    elif (1 - transition_region_width) / 2 < x <= (1 + transition_region_width) / 2:
        return (-np.cos(np.pi/2 * ((x - (1+transition_region_width)/2) /
                                   transition_region_width))**2 + 1)
    else:
        return np.nan


def polar_angle_windows(n_windows, theta_n_steps=100, transition_region_width=.5):
    r"""Create polar angle windows

    We require an integer number of windows placed between 0 and 2 pi.

    Notes
    -----
    Equation 10 from the online methods of [1]_.

    Parameters
    ----------
    n_windows : `int`
        The number of polar angle windows we create.
    theta_n_steps : `int`, optional
        The number of times we sample theta.
    transition_region_width : `float`, optional
        The width of the transition region, parameter :math:`t` in
        equation 9 from the online methods.

    Returns
    -------
    theta : `np.array`
        A 1d array containing the samples of the polar angle:
        ``np.linspace(0, 2*np.pi, theta_n_steps)``
    windows : `np.array`
        A 2d array containing the (1d) polar angle windows. Windows will
        be indexed along the first dimension.

    References
    ----------
    .. [1] Freeman, J., & Simoncelli, E. P. (2011). Metamers of the
       ventral stream. Nature Neuroscience, 14(9),
       1195–1201. http://dx.doi.org/10.1038/nn.2889

    """
    def remap_theta(x):
        if x > np.pi:
            return x - 2*np.pi
        else:
            return x
    theta = np.linspace(0, 2*np.pi, theta_n_steps)
    if int(n_windows) != n_windows:
        raise Exception("n_windows must be an integer!")
    if n_windows == 1:
        raise Exception("We cannot handle one window correctly!")
    # this is `w_\theta` in the paper
    window_width = calc_angular_window_width(n_windows)
    windows = []
    for n in range(int(n_windows)):
        if n == 0:
            tmp_theta = np.array([remap_theta(t) for t in np.linspace(0, 2*np.pi, theta_n_steps)])
        else:
            tmp_theta = theta
        mother_window_arg = ((tmp_theta - (window_width * n +
                                           (window_width * (1-transition_region_width)) / 2)) /
                             window_width)
        windows.append(mother_window(mother_window_arg, transition_region_width))
    windows = [i for i in windows if not np.isnan(i).all()]
    return theta, np.array(windows)


def log_eccentricity_windows(n_windows=None, window_width=None, min_ecc=.5, max_ecc=15,
                             ecc_n_steps=100, transition_region_width=.5):
    r"""Create log eccentricity windows

    Note that exactly one of ``n_windows`` or ``window_width`` must be
    set.

    Notes
    -----
    Equation 11 from the online methods of [1]_.

    Parameters
    ----------
    n_windows : `float` or `None`
        The number of log-eccentricity windows we create. ``n_windows``
        xor ``window_width`` must be set.
    window_width : `float` or `None`
        The width of the log-eccentricity windows. ``n_windows`` xor
        ``window_width`` must be set.
    min_ecc : `float`, optional
        The minimum eccentricity, the eccentricity below which we do not
        compute pooling windows (in degrees). Parameter :math:`e_0` in
        equation 11 of the online methods.
    max_ecc : `float`, optional
        The maximum eccentricity, the outer radius of the image (in
        degrees). Parameter :math:`e_r` in equation 11 of the online
        methods.
    ecc_n_steps : `int`, optional
        The number of times we sample the eccentricity.
    transition_region_width : `float`
        The width of the transition region, parameter :math:`t` in
        equation 9 from the online methods.

    Returns
    -------
    eccentricity : `np.array`
        A 1d array containing the samples of eccentricity:
        ``np.linspace(0, max_ecc, ecc_n_steps)`` (note that the windows
        start having non-NaN values at ``min_ecc`` degrees, but are
        sampled all the way down to 0 degrees)
    windows : `np.array`
        A 2d array containing the (1d) log-eccentricity windows. Windows
        will be indexed along the first dimension.

    References
    ----------
    .. [1] Freeman, J., & Simoncelli, E. P. (2011). Metamers of the
       ventral stream. Nature Neuroscience, 14(9),
       1195–1201. http://dx.doi.org/10.1038/nn.2889

    """
    ecc = np.linspace(0, max_ecc, ecc_n_steps)
    if window_width is None:
        window_width = calc_eccentricity_window_width(min_ecc, max_ecc, n_windows)
    else:
        n_windows = calc_eccentricity_n_windows(window_width, min_ecc, max_ecc)
    windows = []
    for n in range(math.ceil(n_windows)):
        mother_window_arg = (np.log(ecc) - (np.log(min_ecc) + window_width * (n+1))) / window_width
        windows.append(mother_window(mother_window_arg, transition_region_width))
    windows = [i for i in windows if not np.isnan(i).all()]
    return ecc, np.array(windows)


def create_pooling_windows(scaling, min_eccentricity=.5, max_eccentricity=15,
                           radial_to_circumferential_ratio=2, transition_region_width=.5,
                           theta_n_steps=1000, ecc_n_steps=1000, flatten=True):
    r"""Create 2d pooling windows (log-eccentricity by polar angle) that span the visual field

    This creates the pooling windows that we use to average image
    statistics for metamer generation as done in [1]_. This is returned
    as a 3d torch tensor for further use with a model, and will also
    return the theta and eccentricity grids necessary for plotting, if
    desired.

    Note that this is returned in polar coordinates and so if you wish
    to apply it to an image in rectangular coordinates, you'll need to
    make use of pyrtools's ``project_polar_to_cartesian`` function (see
    Examples section)

    Parameters
    ----------
    scaling : `float` or `None`.
        The ratio of the eccentricity window's radial full-width at
        half-maximum to eccentricity (see the `calc_scaling` function).
    min_eccentricity : `float`, optional
        The minimum eccentricity, the eccentricity below which we do not
        compute pooling windows (in degrees). Parameter :math:`e_0` in
        equation 11 of the online methods.
    max_eccentricity : `float`, optional
        The maximum eccentricity, the outer radius of the image (in
        degrees). Parameter :math:`e_r` in equation 11 of the online
        methods.
    radial_to_circumferential_ratio : `float`, optional
        ``scaling`` determines the number of log-eccentricity windows we
        can create; this ratio gives us the number of polar angle
        ones. Based on `scaling`, we calculate the width of the windows
        in log-eccentricity, and then divide that by this number to get
        their width in polar angle. Because we require an integer number
        of polar angle windows, we round the resulting number of polar
        angle windows to the nearest integer, so the ratio in the
        generated windows approximate this. 2 (the default) is the value
        used in the paper [1]_.
    transition_region_width : `float`, optional
        The width of the transition region, parameter :math:`t` in
        equation 9 from the online methods. 0.5 (the default) is the
        value used in the paper [1]_.
    theta_n_steps : `int`, optional
        The number of times we sample theta.
    ecc_n_steps : `int`, optional
        The number of times we sample the eccentricity.
    flatten : bool, optional
        If True, the returned ``windows`` Tensor will be 3d, with
        different windows indexed along the first dimension. If False,
        it will be 4d, with the first dimension corresponding to
        different polar angle windows and the second to different
        eccentricity bands.

    Returns
    -------
    windows : `torch.tensor`
        The 3d or 4d array of 2d windows (in polar angle and
        eccentricity). Whether its 3d or 4d depends on the value of the
        ``flatten`` arg. If True, it will be 3d, with separate windows
        indexed along the first dimension and the shape
        ``(n_polar_windows*n_ecc_windows, ecc_n_steps,
        theta_n_steps)``. If False, it will be 4d, with the shape
        ``(n_polar_windows, n_ecc_windows, ecc_n_steps, theta_n_steps)``
        (where the number of windows is inferred in this function based
        on the values of ``scaling`` and
        ``radial_to_circumferential_width``)
    theta_grid : `torch.tensor`
        The 2d array of polar angle values, as returned by
        meshgrid. Will have the shape ``(ecc_n_steps, theta_n_steps)``
    eccentricity_grid : `torch.tensor`
        The 2d array of eccentricity values, as returned by
        meshgrid. Will have the shape ``(ecc_n_steps, theta_n_steps)``

    Examples
    --------
    To use, simply call with the desired scaling (for the version seen
    in the paper, don't change any of the default arguments; compare
    this image to the right side of Supplementary Figure 1C)

    .. plot::
       :include-source:

       import matplotlib.pyplot as plt
       import plenoptic as po
       windows, theta, ecc = po.simul.create_pooling_windows(.87, theta_n_steps=256,
                                                             ecc_n_steps=256)
       fig, ax = plt.subplots(subplot_kw={'projection': 'polar'})
       for w in windows:
           ax.contour(theta, ecc, w, [.5])
       plt.show()

    If you wish to convert this to the Cartesian coordinates, in order
    to apply to an image, for example, you must use pyrtools's
    ``project_polar_to_cartesian`` function

    .. plot::
       :include-source:

       import matplotlib.pyplot as plt
       import pyrtools as pt
       import plenoptic as po
       windows, theta, ecc = po.simul.create_pooling_windows(.87, theta_n_steps=256,
                                                             ecc_n_steps=256)
       windows_cart = [pt.project_polar_to_cartesian(w) for w in windows]
       pt.imshow(windows_cart, col_wrap=8, zoom=.5)
       plt.show()

    Notes
    -----
    These create the pooling windows, as seen in Supplementary Figure
    1C, in [1]_.

    References
    ----------
    .. [1] Freeman, J., & Simoncelli, E. P. (2011). Metamers of the
       ventral stream. Nature Neuroscience, 14(9),
       1195–1201. http://dx.doi.org/10.1038/nn.2889

    """
    ecc_window_width = calc_eccentricity_window_width(min_eccentricity, max_eccentricity,
                                                      scaling=scaling)
    n_polar_windows = calc_angular_n_windows(ecc_window_width / radial_to_circumferential_ratio)
    # we want to set the number of polar windows where the ratio of widths is approximately what
    # the user specified. the constraint that it's an integer is more important
    theta, angle_tensor = polar_angle_windows(round(n_polar_windows), theta_n_steps,
                                              transition_region_width)
    angle_tensor = torch.tensor(angle_tensor, dtype=torch.float32)
    ecc, ecc_tensor = log_eccentricity_windows(None, ecc_window_width, min_eccentricity,
                                               max_eccentricity, ecc_n_steps,
                                               transition_region_width=transition_region_width)
    ecc_tensor = torch.tensor(ecc_tensor, dtype=torch.float32)
    windows_tensor = torch.einsum('ik,jl->ijkl', [ecc_tensor, angle_tensor])
    if flatten:
        windows_tensor = windows_tensor.reshape((windows_tensor.shape[0] * windows_tensor.shape[1],
                                                 *windows_tensor.shape[2:]))
    theta_grid, ecc_grid = np.meshgrid(theta, ecc)
    theta_grid = torch.tensor(theta_grid, dtype=torch.float32)
    ecc_grid = torch.tensor(ecc_grid, dtype=torch.float32)
    return windows_tensor, theta_grid, ecc_grid


class PoolingWindows(nn.Module):
    r"""Generic class to set up scaling windows for use with other models

    This just generates the pooling windows given a small number of
    parameters. One tricky thing we do is generate a set of scaling
    windows for each scale (appropriately) sized. For example, the V1
    model will have 4 scales, so for a 256 x 256 image, the coefficients
    will have shape (256, 256), (128, 128), (64, 64), and (32,
    32). Therefore, we need windows of the same size (could also
    up-sample the coefficient tensors, but since that would need to
    happen each iteration of the metamer synthesis, pre-generating
    appropriately sized windows is more efficient).

    Parameters
    ----------
    scaling : float
        Scaling parameter that governs the size of the pooling
        windows. Other pooling windows parameters
        (``radial_to_circumferential_ratio``,
        ``transition_region_width``) cannot be set here. If that ends up
        being of interest, will change that.
    img_res : tuple
        The resolution of our image (should therefore contains
        integers). Will use this to generate appropriately sized pooling
        windows.
    min_eccentricity : float, optional
        The eccentricity at which the pooling windows start.
    max_eccentricity : float, optional
        The eccentricity at which the pooling windows end.
    num_scales : int, optional
        The number of scales to generate masks for. For the RGC model,
        this should be 1, otherwise should match the number of scales in
        the steerable pyramid.
    transition_region_width : `float`, optional
        The width of the transition region, parameter :math:`t` in
        equation 9 from the online methods. 0.5 (the default) is the
        value used in the paper [1]_.
    flatten_windows : bool, optional
        If True, each ``windows`` Tensor will be 3d, with
        different windows indexed along the first dimension. If False,
        it will be 4d, with the first dimension corresponding to
        different polar angle windows and the second to different
        eccentricity bands.

    Attributes
    ----------
    scaling : float
        Scaling parameter that governs the size of the pooling windows.
    min_eccentricity : float
        The eccentricity at which the pooling windows start.
    max_eccentricity : float
        The eccentricity at which the pooling windows end.
    transition_region_width : `float`, optional
        The width of the transition region, parameter :math:`t` in
        equation 9 from the online methods.
    windows : list
        A list of 3d or 4d tensors containing the pooling windows in
        which the model parameters are averaged. Each entry in the list
        corresponds to a different scale and thus is a different size
        (though they should all have the same number of windows)
    state_dict_reduced : dict
        A dictionary containing those attributes necessary to initialize
        the model, plus a 'model_name' field which the ``load_reduced``
        method uses to determine which model constructor to call. This
        is used for saving/loading the models, since we don't want to
        keep the (very large) representation and intermediate steps
        around. To save, use ``self.save_reduced(filename)``, and then
        load from that same file using the class method
        ``po.simul.VentralModel.load_reduced(filename)``
    window_width_degrees : dict
        Dictionary containing the widths of the windows in
        degrees. There are four keys: 'radial_top', 'radial_full',
        'angular_top', and 'angular_full', corresponding to a 2x2 for
        the widths in the radial and angular directions by the 'top' and
        'full' widths (top is the width of the flat-top region of each
        window, where the window's value is 1; full is the width of the
        entire window). Each value is a list containing the widths for
        the windows in different eccentricity bands. To visualize these,
        see the ``plot_window_sizes`` method.
    window_width_pixels : list
        List of dictionaries containing the widths of the windows in
        pixels; each entry in the list corresponds to the widths for a
        different scale, as in ``windows``. See above for explanation of
        the dictionaries. To visualize these, see the
        ``plot_window_sizes`` method.
    n_polar_windows : int
        The number of windows we have in the polar angle dimension
        (within each eccentricity band)
    n_eccentricity_bands : int
        The number of eccentricity bands in our model

    """
    def __init__(self, scaling, img_res, min_eccentricity=.5, max_eccentricity=15, num_scales=1,
                 transition_region_width=.5, flatten_windows=True):
        super().__init__()
        if len(img_res) != 2:
            raise Exception("img_res must be 2d!")
        if img_res[0] != img_res[1]:
            warnings.warn("The windows must be created square initially, so we'll do that and then"
                          " crop them down to the proper size")
            window_res = 2*[np.max(img_res)]
        else:
            window_res = img_res
        self.scaling = scaling
        self.transition_region_width = transition_region_width
        self.min_eccentricity = min_eccentricity
        self.max_eccentricity = max_eccentricity
        self.windows = []
        self.window_width_pixels = []
        ecc_window_width = calc_eccentricity_window_width(min_eccentricity, max_eccentricity,
                                                          scaling=scaling)
        self.n_polar_windows = round(calc_angular_n_windows(ecc_window_width / 2))
        angular_window_width = calc_angular_window_width(self.n_polar_windows)
        window_widths = calc_window_widths_actual(angular_window_width, ecc_window_width,
                                                  min_eccentricity, max_eccentricity,
                                                  transition_region_width)
        self.window_width_degrees = dict(zip(['radial_top', 'radial_full', 'angular_top',
                                              'angular_full'], window_widths))
        self.state_dict_reduced = {'scaling': scaling, 'img_res': img_res,
                                   'min_eccentricity': min_eccentricity,
                                   'max_eccentricity': max_eccentricity,
                                   'transition_region_width': transition_region_width}
        for i in range(num_scales):
            scaled_window_res = [np.ceil(j / 2**i) for j in window_res]
            windows, theta, ecc = create_pooling_windows(
                scaling, min_eccentricity, max_eccentricity, ecc_n_steps=scaled_window_res[0],
                theta_n_steps=scaled_window_res[1], flatten=flatten_windows,
                transition_region_width=transition_region_width)

            # need this to be float32 so we can divide the representation by it.
            if windows.ndimension() == 3:
                windows = torch.tensor([pt.project_polar_to_cartesian(w) for w in windows],
                                       dtype=torch.float32)
            elif windows.ndimension() == 4:
                # this is a little more complicated because we want to
                # keep the structure we have before
                windows_tmp = []
                for j in windows:
                    windows_tmp.append([pt.project_polar_to_cartesian(w) for w in j])
                windows = torch.tensor(windows_tmp, dtype=torch.float32)
            if img_res[0] != window_res[0]:
                slice_vals = PoolingWindows._get_slice_vals(scaled_window_res[0], img_res[0], i)
                windows = windows[..., slice_vals[0]:slice_vals[1], :]
            elif img_res[1] != window_res[1]:
                slice_vals = PoolingWindows._get_slice_vals(scaled_window_res[1], img_res[1], i)
                windows = windows[..., slice_vals[0]:slice_vals[1]]
            self.windows.append(windows)
            # we convert from degrees to pixels here, by multiplying the
            # width in degrees by (radius in pixels) / (radius in degrees)
            deg_to_pix = (img_res[0] / (2**(i+1))) / max_eccentricity
            # each value is a list, so we need to use list comprehension
            # to scale them all appropriately
            self.window_width_pixels.append(dict((k, [i*deg_to_pix for i in v]) for k, v in
                                                 self.window_width_degrees.copy().items()))
        self.n_eccentricity_bands = int(self.windows[0].shape[0] // self.n_polar_windows)

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
        for i, w in enumerate(self.windows):
            self.windows[i] = w.to(*args, **kwargs)
        return self

    @staticmethod
    def _get_slice_vals(scaled_window_res, img_res, scale):
        r"""Helper function to find the values to use when slicing windows down to size

        If we have a non-square image, we must create the windows as a
        square array and then slice it down to the size of the image,
        retaining the center of the windows array.

        The one wrinkle on this is that we also sometimes need to do
        this for different scales, so we need to make sure that
        'down-sampled' windows we create have the same shape as those
        created by our pyramid methods. It looks like that's always the
        ceiling of shape/2**scale. NOTE: This means it will probably not
        work if you're using something else that has multiple scales
        that doesn't use our pyramid methods and thus ends up with
        slightly differently sized down-sampled components. On images
        that are a power of 2, this shouldn't be an issue regardless

        This will only be for one dimension; because of how we've
        constructed the windows, we know they only need to be cut down
        in a single dimension

        Parameters
        ----------
        scaled_window_res : float
            The size of the square 'down-sampled'/scaled window we
            created (in one dimension; this should not be a tuple).
        img_res : float
            The size of the 'down-sampled'/scaled image we want to match
            (in one dimension; this should not be a tuple).

        Returns
        -------
        slice_vals : list
            A list of ints, use this to slice the window down correctly, e.g.,
            ``window[..., slice_vals[0]:slice_vals[1]]``

        """
        slice_vals = (scaled_window_res - np.ceil(img_res/2**scale)) / 2
        return [int(np.floor(slice_vals)), -int(np.ceil(slice_vals))]

    def forward(self, x, idx=0):
        r"""Window and pool the input

        We take an input, either a 4d tensor or a dictionary of 4d
        tensors, and return a windowed version of it. If it's a 4d
        tensor, we return a 5d or 6d tensor, with windows indexed along
        the 3rd or 3rd and 4th dimension. If it's a dictionary, we
        return a dictionary with the same keys and have changed all the
        values to 5d or 6d tensors, with windows indexed along the 3rd
        or 3rd and 4th dimension(s)

        Whether we return a 5d or 6d tensor depends on the value of the
        ``flatten_windows`` during initialization.

        If it's a 4d tensor, we use the ``idx`` entry in the ``windows``
        list. If it's a dictionary, we assume it's keys are ``(scale,
        orientation)`` tuples and so use ``windows[key[0]]`` to find the
        appropriately-sized window (this is the case for, e.g., the
        steerable pyramid). If we want to use differently-structured
        dictionaries, we'll need to restructure this

        This is equivalent to calling ``self.pool(self.window(x, idx),
        idx)``

        Parameters
        ----------
        x : dict or torch.Tensor
            Either a 4d tensor or a dictionary of 4d tensors.
        idx : int, optional
            Which entry in the ``windows`` list to use. Only used if
            ``x`` is a tensor

        Returns
        -------
        pooled_x : dict or torch.Tensor
            Same type as ``x``, see above for how it's created.

        See also
        --------
        window : window the input
        pool : pool the windowed input (get the weighted average)

        """
        windowed_x = self.window(x, idx)
        return self.pool(windowed_x, idx)

    def window(self, x, idx=0):
        r"""Window the input

        We take an input, either a 4d tensor or a dictionary of 4d
        tensors, and return a windowed version of it. If it's a 4d
        tensor, we return a 5d or 6d tensor, with windows indexed along
        the 3rd or 3rd and 4th dimension. If it's a dictionary, we
        return a dictionary with the same keys and have changed all the
        values to 5d or 6d tensors, with windows indexed along the 3rd
        or 3rd and 4th dimension(s)

        Whether we return a 5d or 6d tensor depends on the value of the
        ``flatten_windows`` during initialization.

        If it's a 4d tensor, we use the ``idx`` entry in the ``windows``
        list. If it's a dictionary, we assume it's keys are ``(scale,
        orientation)`` tuples and so use ``windows[key[0]]`` to find the
        appropriately-sized window (this is the case for, e.g., the
        steerable pyramid). If we want to use differently-structured
        dictionaries, we'll need to restructure this

        Parameters
        ----------
        x : dict or torch.Tensor
            Either a 4d tensor or a dictionary of 4d tensors.
        idx : int, optional
            Which entry in the ``windows`` list to use. Only used if
            ``x`` is a tensor

        Returns
        -------
        windowed_x : dict or torch.Tensor
            Same type as ``x``, see above for how it's created.

        See also
        --------
        pool : pool the windowed input (get the weighted average)
        forward : perform the windowing and pooling simultaneously

        """
        if self.windows[0].ndimension() == 3:
            ein_str = 'ijkl,wkl->ijwkl'
        elif self.windows[0].ndimension() == 4:
            ein_str = 'ijkl,wvkl->ijwvkl'
        if isinstance(x, dict):
            if list(x.values())[0].ndimension() != 4:
                raise Exception("PoolingWindows input must be 4d tensors or a dict of 4d tensors!"
                                " Unsqueeze until this is true!")
            # one way to make this more general: figure out the size of
            # the tensors in x and in self.windows, and intelligently
            # lookup which should be used.
            return dict((k, torch.einsum(ein_str, [v, self.windows[k[0]]]))
                        for k, v in x.items())
        else:
            if x.ndimension() != 4:
                raise Exception("PoolingWindows input must be 4d tensors or a dict of 4d tensors!"
                                " Unsqueeze until this is true!")
            return torch.einsum(ein_str, [x, self.windows[idx]])

    def pool(self, windowed_x, idx=0):
        r"""Pool the windowed input

        We take the windowed input (as returned by ``self.window()``)
        and perform a weighted average, dividing each windowed statistic
        by the sum of the window that generated it.

        The input must either be a 5d/6d tensor or a dictionary of 5d/6d
        tensors and we collapse across the spatial dimensions, returning
        a 3d/4d tensor or a dictionary of 3d/4d tensors.

        We return a 3d tensor if the input was 5d and a 4d tensor if it
        was 6d (since we're averaging over the last two dimensions, the
        spatial ones). This ultimately depends on the value of the
        ``flatten_windows`` during initialization.

        Similar to ``self.window()``, if it's a tensor, we use the
        ``idx`` entry in the ``windows`` list. If it's a dictionary, we
        assume it's keys are ``(scale, orientation)`` tuples and so use
        ``windows[key[0]]`` to find the appropriately-sized window (this
        is the case for, e.g., the steerable pyramid). If we want to use
        differently-structured dictionaries, we'll need to restructure
        this

        Parameters
        ----------
        windowed_x : dict or torch.Tensor
            Either a 5d tensor or a dictionary of 5d tensors
        idx : int, optional
            Which entry in the ``windows`` list to use. Only used if
            ``x`` is a tensor

        Returns
        -------
        pooled_x : dict or torch.Tensor
            Same type as ``windowed_x``, see above for how it's created.

        See also
        --------
        window : window the input
        forward : perform the windowing and pooling simultaneously

        """
        if isinstance(windowed_x, dict):
            # one way to make this more general: figure out the size of
            # the tensors in x and in self.windows, and intelligently
            # lookup which should be used.
            divisor = {}
            # If a window is completely off the image, then the sum of
            # its elements will be 0, which gives us a nan when we
            # divide by it. To avoid this, we set this to 1 (the
            # corresponding numerator will be 0, so it doesn't matter
            # what we set it to)
            for k in windowed_x.keys():
                d = self.windows[k[0]].sum((-1, -2))
                d[d == 0] = 1
                divisor[k] = d
            return dict((k, v.sum((-1, -2)) / divisor[k])
                        for k, v in windowed_x.items())
        else:
            divisor = self.windows[idx].sum((-1, -2))
            # If a window is completely off the image, then the sum of
            # its elements will be 0, which gives us a nan when we
            # divide by it. To avoid this, we set this to 1 (the
            # corresponding numerator will be 0, so it doesn't matter
            # what we set it to)
            divisor[divisor == 0] = 1
            return windowed_x.sum((-1, -2)) / divisor

    def plot_windows(self, ax, contour_levels=[.5], colors='r', **kwargs):
        r"""plot the pooling windows on an image.

        This is just a simple little helper to plot the pooling windows
        on an existing axis. The use case is overlaying this on top of
        the image we're pooling (as returned by ``pyrtools.imshow``),
        and so we require an axis to be passed

        Any additional kwargs get passed to ``ax.contour``

        Parameters
        ----------
        ax : matplotlib.pyplot.axis
            The existing axis to plot the windows on
        contour_levels : array-like or int, optional
            The ``levels`` argument to pass to ``ax.contour``. From that
            documentation: "Determines the number and positions of the
            contour lines / regions. If an int ``n``, use ``n`` data
            intervals; i.e. draw ``n+1`` contour lines. The level
            heights are automatically chosen. If array-like, draw
            contour lines at the specified levels. The values must be in
            increasing order". ``[.5]`` (the default) is recommended for
            these windows.
        colors : color string or sequence of colors, optional
            The ``colors`` argument to pass to ``ax.contour``. If a
            single character, all will have the same color; if a
            sequence, will cycle through the colors in ascending order
            (repeating if necessary)

        Returns
        -------
        ax : matplotlib.pyplot.axis
            The axis with the windows

        """
        # this will make sure our windows tensor is 3d: windows, height, width
        for w in self.windows[0].flatten(0, -3):
            ax.contour(w.detach(), contour_levels, colors=colors, **kwargs)
        return ax

    def plot_window_sizes(self, units='degrees', scale_num=0, figsize=(5, 5), jitter=.25):
        r"""plot the size of the windows, in degrees or pixels

        We plot the size of the window in both angular and radial
        direction, as well as showing both the 'top' and 'full' width
        (top is the width of the flat-top region of each window, where
        the window's value is 1; full is the width of the entire window)

        We plot this as a stem plot against eccentricity, showing the
        windows at their central eccentricity

        If the unit is 'pixels', then we also need to know which
        ``scale_num`` to plot (the windows are created at different
        scales, and so come in different pixel sizes)

        Parameters
        ----------
        units : {'degrees', 'pixels'}, optional
            Whether to show the information in degrees or pixels (both
            the width and the window location will be presented in the
            same unit).
        scale_num : int, optional
            Which scale window we should plot
        figsize : tuple, optional
            The size of the figure to create
        jitter : float or None, optional
            Whether to add a little bit of jitter to the x-axis to
            separate the radial and angular widths. There are only two
            values we separate, so we don't add actual jitter, just move
            one up by the value specified by jitter, the other down by
            that much (we use the same value at each eccentricity)

        Returns
        -------
        fig : matplotlib.figure.Figure
            The figure containing the plot

        """
        if units == 'degrees':
            data = self.window_width_degrees
        elif units == 'pixels':
            data = self.window_width_pixels[scale_num]
        else:
            raise Exception("units must be one of {'pixels', 'degrees'}, not %s!" % units)
        ecc_window_width = calc_eccentricity_window_width(self.min_eccentricity,
                                                          self.max_eccentricity,
                                                          scaling=self.scaling)
        central_ecc = calc_windows_central_eccentricity(len(data['radial_top']), ecc_window_width,
                                                        self.min_eccentricity)
        fig, ax = plt.subplots(1, 1, figsize=figsize)
        if jitter is not None:
            jitter_vals = {'radial': -jitter, 'angular': jitter}
        else:
            jitter_vals = {'radial': 0, 'angular': 0}
        keys = ['radial_top', 'radial_full', 'angular_top', 'angular_full']
        marker_styles = ['C0o', 'C0.', 'C1o', 'C1.']
        line_styles = ['C0-', 'C0-', 'C1-', 'C1-']
        for k, m, l in zip(keys, marker_styles, line_styles):
            ax.stem(np.array(central_ecc)+jitter_vals[k.split('_')[0]], data[k], l, m, label=k,
                    use_line_collection=True)
        ax.set_ylabel('Window size (%s)' % units)
        ax.set_xlabel('Window central eccentricity (%s)' % units)
        ax.legend(loc='upper left')
        return fig
