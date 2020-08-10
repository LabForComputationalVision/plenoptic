import torch
import numpy as np
from pyrtools import synthetic_images, blurDn
import matplotlib.pyplot as plt
import os.path as op
from .signal import rescale


DATA_PATH = op.join(op.dirname(op.realpath(__file__)), '..', '..', 'data')


def to_numpy(x):
    r"""cast tensor to numpy in the most conservative way possible

    Parameters
    ----------------
    x: `torch.Tensor`
       Tensor to be converted to `numpy.ndarray` on CPU.
    """

    try:
        x = x.detach().cpu().numpy().astype(np.float32)
    except AttributeError:
        # in this case, it's already a numpy array
        pass
    return x


def torch_complex_to_numpy(x):
    r""" convert a torch complex tensor (written as two stacked real and imaginary tensors)
    to a numpy complex array

    Parameters
    ----------------------
    x: `torch.Tensor`
        Tensor whose last dimension is size 2 where first component is the real component and the second is the
        imaginary component.
    """

    x_np = to_numpy(x)
    x_np = x_np[...,0] + 1j * x_np[...,1]
    return x_np


def convert_pyr_to_tensor(pyr_coeffs, exclude = [], is_complex = True):
    r""" Function that takes a torch pyramid and converts the output into a single tensor
    of `torch.Size([B, C, H, W])` for use in an `nn.Module` downstream.

    Parameters
    ----------
    pyr_coeffs: `OrderedDict`
        Steerable pyramid coefficients
    exclude: `list`
        List of bands to include, can include 'residual_lowpass', 'residual_highpass' or tuple (ind, ind).
    is_complex: `bool`
        Boolean indicating whether or not complex pyramid is used.
    """

    coeff_list = []
    coeff_list_resid = []
    for k in pyr_coeffs.keys():
        if k not in exclude:
            if 'residual' in k:
                coeff_list_resid.append(pyr_coeffs[k])
            else:
                coeff_list.append(pyr_coeffs[k])

    coeff_bands = torch.cat(coeff_list, dim=1)
    batch_size = coeff_bands.shape[0]
    imshape = [coeff_bands.shape[2], coeff_bands.shape[3]]
    if is_complex:
        coeff_bands = coeff_bands.permute(0,1,4,2,3).contiguous().view(batch_size,-1,imshape[0],imshape[1])
    if len(coeff_list_resid) > 0:
        coeff_resid = torch.cat(coeff_list_resid, dim=1)
        coeff_out = torch.cat([coeff_bands, coeff_resid], dim=1)
    else:
        coeff_out = coeff_bands

    return coeff_out


def make_basic_stimuli(size=256, requires_grad=True):
    r""" Make basic stimuli for testing models etc.

    Parameters
    ----------
    size: `int`
        Stimulus will have `torch.Size([size, size])`
    requires_grad: `bool`
        Does the image require gradients
    """
    assert size in [32, 64, 128, 256, 512], 'size not supported'
    impulse = np.zeros((size, size))
    impulse[size // 2, size // 2] = 1

    step_edge = synthetic_images.square_wave(size=size, period=size + 1, direction=0, amplitude=1, phase=0)

    ramp = synthetic_images.ramp(size=size, direction=np.pi / 2, slope=1)

    bar = np.zeros((size, size))
    bar[size // 2 - size//10:size // 2 + size//10, size // 2 - 1:size // 2 + 1] = 1

    curv_edge = synthetic_images.disk(size=size, radius=size / 1.2, origin=(size, size))

    sine_grating = synthetic_images.sine(size) * synthetic_images.gaussian(size, covariance=size)

    square_grating = synthetic_images.square_wave(size, frequency=(.5, .5), phase=2 * np.pi / 3.)
    square_grating *= synthetic_images.gaussian(size, covariance=size)

    polar_angle = synthetic_images.polar_angle(size)

    angular_sine = synthetic_images.angular_sine(size, 6)

    zone_plate = synthetic_images.zone_plate(size)

    fract = synthetic_images.pink_noise(size, fract_dim=.8)

    checkerboard = plt.imread(op.join(DATA_PATH, 'checkerboard.pgm')).astype(float)
    # adjusting form 256 to desired size
    l = int(np.log2(256 // size))
    # for larger size use upConv
    checkerboard = blurDn(checkerboard, l, 'qmf9')

    sawtooth = plt.imread(op.join(DATA_PATH, 'sawtooth.pgm')).astype(float)
    sawtooth = blurDn(sawtooth, l, 'qmf9')

    reptil_skin = plt.imread(op.join(DATA_PATH, 'reptil_skin.pgm')).astype(float)
    reptil_skin = blurDn(reptil_skin, l, 'qmf9')

    image = plt.imread(op.join(DATA_PATH, 'einstein.png')).astype(float)[:,:,0]
    image = blurDn(image, l, 'qmf9')

    # image = plt.imread('/Users/pe/Pictures/umbrella.jpg').astype(float)
    # image = image[500:500+2**11,1000:1000+2**11,0]
    # image = pt.blurDn(image, 4, 'qmf9')

    stim = [impulse, step_edge, ramp, bar, curv_edge,
            sine_grating, square_grating, polar_angle, angular_sine, zone_plate,
            fract, checkerboard, sawtooth, reptil_skin, image]
    stim = [rescale(s) for s in stim]

    stimuli = torch.cat(
        [torch.tensor(s, dtype=torch.float32, requires_grad=requires_grad).unsqueeze(0).unsqueeze(0) for s in stim],
        dim=0)

    return stimuli


if __name__ == '__main__':
    make_basic_stimuli()
