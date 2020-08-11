import numpy as np
import torch
import pyrtools as pt


def rescale(x, a=0, b=1):
    """
    Linearly rescale the dynamic of a vector to the range [a,b]
    """
    v = x.max() - x.min()
    g = (x - x.min()) #.clone()
    if v > 0:
        g = g / v
    return a + g * (b-a)


def roll_n(X, axis, n):
    f_idx = tuple(slice(None, None, None) if i != axis else slice(0, n, None) for i in range(X.dim()))
    b_idx = tuple(slice(None, None, None) if i != axis else slice(n, None, None) for i in range(X.dim()))
    front = X[f_idx]
    back = X[b_idx]
    return torch.cat([back, front], axis)


def batch_fftshift2d(x):
    real, imag = torch.unbind(x, -1)
    for dim in range(1, len(real.size())):
        n_shift = real.size(dim)//2
        if real.size(dim) % 2 != 0:
            n_shift += 1  # for odd-sized images
        real = roll_n(real, axis=dim, n=n_shift)
        imag = roll_n(imag, axis=dim, n=n_shift)
    # preallocation is much faster than using stack
    shifted = torch.empty((*real.shape, 2), device=real.device)
    shifted[..., 0] = real
    shifted[..., 1] = imag
    return shifted  # last dim=2 (real&imag)


def batch_ifftshift2d(x):
    real, imag = torch.unbind(x, -1)
    for dim in range(len(real.size()) - 1, 0, -1):
        real = roll_n(real, axis=dim, n=real.size(dim)//2)
        imag = roll_n(imag, axis=dim, n=imag.size(dim)//2)
    # preallocation is much faster than using stack
    shifted = torch.empty((*real.shape, 2), device=real.device)
    shifted[..., 0] = real
    shifted[..., 1] = imag
    return shifted  # last dim=2 (real&imag)


def rcosFn(width=1, position=0, values=(0, 1)):
    '''Return a lookup table containing a "raised cosine" soft threshold function

    Y =  VALUES(1) + (VALUES(2)-VALUES(1)) * cos^2( PI/2 * (X - POSITION + WIDTH)/WIDTH )

    this lookup table is suitable for use by `pointOp`

    Arguments
    ---------
    width : `float`
        the width of the region over which the transition occurs
    position : `float`
        the location of the center of the threshold
    values : `tuple`
        2-tuple specifying the values to the left and right of the transition.

    Returns
    -------
    X : `np.array`
        the x valuesof this raised cosine
    Y : `np.array`
        the y valuesof this raised cosine
    '''

    sz = 256   # arbitrary!

    X = np.pi * np.arange(-sz-1, 2) / (2*sz)

    Y = values[0] + (values[1]-values[0]) * np.cos(X)**2

    # make sure end values are repeated, for extrapolation...
    Y[0] = Y[1]
    Y[sz+2] = Y[sz+1]

    X = position + (2*width/np.pi) * (X + np.pi/4)

    return X, Y


def pointOp(im, Y, X):
    out = np.interp(im.flatten(), X, Y )

    return np.reshape(out, im.shape)


def rectangular_to_polar(real, imaginary):
    """Rectangular to polar coordinate transform

    Argument
    --------
    real: torch.Tensor
        tensor containing the real component
    imaginary: torch.Tensor
        tensor containing the imaginary component
    Returns
    -------
    amplitude: torch.Tensor
        tensor containing the amplitude (aka. complex modulus)
    phase: torch.Tensor
        tensor containing the phase
    Note
    ----
    Since complex numbers are not supported by pytorch, this function expects two tensors of the same shape.
    One containing the real component, one containing the imaginary component. This means that if complex
    numbers are represented as an extra dimension in the tensor of interest, the user needs to index through
    that dimension.
    """
    amplitude = torch.sqrt(real ** 2 + imaginary ** 2)
    phase = torch.atan2(imaginary, real)
    return amplitude, phase


def polar_to_rectangular(amplitude, phase):
    """Polar to rectangular coordinate transform

    Argument
    --------
    amplitude: torch.Tensor
        tensor containing the amplitude (aka. complex modulus). Must be > 0.
    phase: torch.Tensor
        tensor containing the phase
    Returns
    -------
    real: torch.Tensor
        tensor containing the real component
    imaginary: torch.Tensor
        tensor containing the imaginary component
    Note
    ----
    Since complex numbers are not supported by pytorch, this function returns two tensors of the same shape.
    One containing the real component, one containing the imaginary component.
    """
    if (amplitude<=0).any():
        raise ValueError("Amplitudes must be strictly positive.")

    real = amplitude * torch.cos(phase)
    imaginary = amplitude * torch.sin(phase)
    return real, imaginary


def power_spectrum(x, log=True):

    sp = torch.rfft(x, signal_ndim=2, onesided=False)
    sp = batch_fftshift2d(sp)
    sp_power = (sp[..., 0]**2 + sp[..., 1]**2)
    if log:
        sp_power[sp_power < 1e-5] += 1e-5
        sp_power = torch.log(sp_power)

    return sp_power


def make_disk(imgSize, outerRadius=None, innerRadius=None):

    if outerRadius is None:
        outerRadius = (imgSize-1) / 2

    if innerRadius is None:
        innerRadius = outerRadius / 2

    mask = torch.Tensor( imgSize, imgSize )
    imgCenter = ( imgSize - 1 ) / 2

    for i in range( imgSize ):
        for j in range( imgSize ):

            r = np.sqrt( (i-imgCenter)**2 + (j-imgCenter)**2 )

            if r > outerRadius:
                mask[i][j] = 0
            elif r < innerRadius:
                mask[i][j] = 1
            else:
                mask[i][j] = ( 1 + np.cos( np.pi * ( r - innerRadius ) / ( outerRadius - innerRadius ) ) ) / 2

    return mask


def kurtosis(mtx):
    # implementation is only for real components
    return torch.mean(torch.abs(mtx-mtx.mean()).pow(4))/(mtx.var().pow(2))


def skew(mtx):
    return torch.mean((mtx-mtx.mean()).pow(3))/(mtx.var().pow(1.5))


def add_noise(img, noise_mse):
    """Add normally distributed noise to an image

    This adds normally-distributed noise to an image so that the resulting
    noisy version has the specified mean-squared error.

    Parameters
    ----------
    img : torch.Tensor
        the image to make noisy
    noise_mse : float or list
        the target MSE value / variance of the noise. More than one value is
        allowed

    Returns
    -------
    noisy_img : torch.Tensor
        the noisy image. If `noise_mse` contains only one element, this will be
        the same size as `img`. Else, each separate value from `noise_mse` will
        be along the batch dimension.

    """
    noise_mse = torch.tensor(noise_mse, dtype=torch.float32).unsqueeze(0)
    noise_mse = noise_mse.view(noise_mse.nelement(), 1, 1, 1)
    noise = 200 * torch.randn(max(noise_mse.shape[0], img.shape[0]), *img.shape[1:])
    noise = noise - noise.mean()
    noise = noise * torch.sqrt(noise_mse / (noise**2).mean((-1, -2)).unsqueeze(-1).unsqueeze(-1))
    return img + noise
