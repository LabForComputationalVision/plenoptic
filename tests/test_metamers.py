#!/usr/bin/env python3

import os.path as op
import torch
import plenoptic as po
import matplotlib.pyplot as plt
import pytest
import numpy as np

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
dtype = torch.float32
DATA_DIR = op.join(op.dirname(op.realpath(__file__)), '..', 'data')
print("On device %s" % device)


class TestMetamers(object):

    def test_metamer_save_load(self, tmp_path):

        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        v1 = po.simul.PrimaryVisualCortex(.5, im.shape[2:])
        v1 = v1.to(device)
        metamer = po.synth.Metamer(im, v1)
        metamer.synthesize(max_iter=3, store_progress=True)
        metamer.save(op.join(tmp_path, 'test_metamer_save_load.pt'))
        met_copy = po.synth.Metamer.load(op.join(tmp_path, "test_metamer_save_load.pt"),
                                         map_location=device)
        for k in ['target_image', 'saved_representation', 'saved_image', 'matched_representation',
                  'matched_image', 'target_representation']:
            if not getattr(metamer, k).allclose(getattr(met_copy, k)):
                raise Exception("Something went wrong with saving and loading! %s not the same"
                                % k)

    def test_metamer_save_load_reduced(self, tmp_path):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=torch.float32, device=device).unsqueeze(0).unsqueeze(0)
        v1 = po.simul.PrimaryVisualCortex(.5, im.shape[2:])
        v1 = v1.to(device)
        metamer = po.synth.Metamer(im, v1)
        metamer.synthesize(max_iter=3, store_progress=True)
        metamer.save(op.join(tmp_path, 'test_metamer_save_load_reduced.pt'), True)
        with pytest.raises(Exception):
            met_copy = po.synth.Metamer.load(op.join(tmp_path,
                                                     "test_metamer_save_load_reduced.pt"))
        met_copy = po.synth.Metamer.load(op.join(tmp_path, 'test_metamer_save_load_reduced.pt'),
                                         po.simul.PrimaryVisualCortex.from_state_dict_reduced,
                                         map_location=device)
        for k in ['target_image', 'saved_representation', 'saved_image', 'matched_representation',
                  'matched_image', 'target_representation']:
            if not getattr(metamer, k).allclose(getattr(met_copy, k)):
                raise Exception("Something went wrong with saving and loading! %s not the same" % k)

    def test_metamer_store_rep(self):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        v1 = po.simul.PrimaryVisualCortex(.5, im.shape[2:])
        v1 = v1.to(device)
        metamer = po.synth.Metamer(im, v1)
        metamer.synthesize(max_iter=3, store_progress=2)

    def test_metamer_store_rep_2(self):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        v1 = po.simul.PrimaryVisualCortex(.5, im.shape[2:])
        v1 = v1.to(device)
        metamer = po.synth.Metamer(im, v1)
        metamer.synthesize(max_iter=3, store_progress=True)

    def test_metamer_store_rep_3(self):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        v1 = po.simul.PrimaryVisualCortex(.5, im.shape[2:])
        v1 = v1.to(device)
        metamer = po.synth.Metamer(im, v1)
        metamer.synthesize(max_iter=6, store_progress=3)

    def test_metamer_store_rep_4(self):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        v1 = po.simul.PrimaryVisualCortex(.5, im.shape[2:])
        v1 = v1.to(device)
        metamer = po.synth.Metamer(im, v1)
        with pytest.raises(Exception):
            metamer.synthesize(max_iter=3, store_progress=False, save_progress=True)

    def test_metamer_plotting_v1(self):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        v1 = po.simul.PrimaryVisualCortex(.5, im.shape[2:])
        v1 = v1.to(device)
        metamer = po.synth.Metamer(im, v1)
        metamer.synthesize(max_iter=6, store_progress=True)
        metamer.plot_representation_error()
        metamer.model.plot_representation_image(data=metamer.representation_error())
        metamer.plot_synthesis_status()
        metamer.plot_synthesis_status(iteration=1)

    def test_metamer_plotting_rgc(self):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        rgc = po.simul.RetinalGanglionCells(.5, im.shape[2:])
        rgc = rgc.to(device)
        metamer = po.synth.Metamer(im, rgc)
        metamer.synthesize(max_iter=6, store_progress=True)
        metamer.plot_representation_error()
        metamer.model.plot_representation_image(data=metamer.representation_error())
        metamer.plot_synthesis_status()
        metamer.plot_synthesis_status(iteration=1)

    def test_metamer_continue(self):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        rgc = po.simul.RetinalGanglionCells(.5, im.shape[2:])
        rgc = rgc.to(device)
        metamer = po.synth.Metamer(im, rgc)
        metamer.synthesize(max_iter=3, store_progress=True)
        metamer.synthesize(max_iter=3, store_progress=True,
                           initial_image=metamer.matched_image.detach().clone())

    def test_metamer_animate(self):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        rgc = po.simul.RetinalGanglionCells(.5, im.shape[2:])
        rgc = rgc.to(device)
        metamer = po.synth.Metamer(im, rgc)
        metamer.synthesize(max_iter=3, store_progress=True)
        # this will test several related functions for us:
        # plot_synthesis_status, plot_representation_error,
        # representation_error
        metamer.animate(figsize=(17, 5), plot_representation_error=True, ylim='rescale100',
                        framerate=40)

    def test_metamer_save_progress(self, tmp_path):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im, dtype=torch.float32, device=device).unsqueeze(0).unsqueeze(0)
        v1 = po.simul.PrimaryVisualCortex(.5, im.shape[2:])
        v1 = v1.to(device)
        metamer = po.synth.Metamer(im, v1)
        save_path = op.join(tmp_path, 'test_metamer_save_progress.pt')
        metamer.synthesize(max_iter=3, store_progress=True, save_progress=True,
                           save_path=save_path)
        po.synth.Metamer.load(save_path, po.simul.PrimaryVisualCortex.from_state_dict_reduced)

    def test_metamer_fraction_removed(self):

        X = np.load(op.join(op.join(op.dirname(op.realpath(__file__)), '..', 'examples'), 'metamer_PS_samples.npy'))
        sigma = X.std(axis=1)
        sigma[sigma < .00001] = 1
        normalizationFactor = 1 / sigma
        normalizationFactor = torch.diag(torch.tensor(normalizationFactor, dtype=torch.float32))

        model = po.simul.Texture_Statistics([256, 256], normalizationFactor=normalizationFactor)
        image = plt.imread(op.join(DATA_DIR, 'nuts.pgm')).astype(float) / 255.
        im0 = torch.tensor(image, requires_grad=True, dtype=torch.float32).squeeze().unsqueeze(0).unsqueeze(0)
        c = po.RangeClamper([image.min(), image.max()])
        M = po.synth.Metamer(im0, model)

        matched_image, matched_representation = M.synthesize(max_iter=3, learning_rate=1, seed=1, optimizer='SGD',
                                                             fraction_removed=.1, clamper=c)

    def test_metamer_loss_change(self):
        # literally just testing that it runs
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        rgc = po.simul.RetinalGanglionCells(.5, im.shape[2:])
        rgc = rgc.to(device)
        metamer = po.synth.Metamer(im, rgc)
        metamer.synthesize(max_iter=10, loss_change_iter=1, loss_change_thresh=1,
                           loss_change_fraction=.5)
        metamer.synthesize(max_iter=10, loss_change_iter=1, loss_change_thresh=1,
                           loss_change_fraction=.5, fraction_removed=.1)

    def test_metamer_coarse_to_fine(self):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        v1 = po.simul.PrimaryVisualCortex(.5, im.shape[2:])
        v1 = v1.to(device)
        metamer = po.synth.Metamer(im, v1)
        metamer.synthesize(max_iter=10, loss_change_iter=1, loss_change_thresh=10,
                           coarse_to_fine=True)
        metamer.synthesize(max_iter=10, loss_change_iter=1, loss_change_thresh=10,
                           coarse_to_fine=True, fraction_removed=.1)
        metamer.synthesize(max_iter=10, loss_change_iter=1, loss_change_thresh=10,
                           coarse_to_fine=True, loss_change_fraction=.5)
        metamer.synthesize(max_iter=10, loss_change_iter=1, loss_change_thresh=10,
                           coarse_to_fine=True, loss_change_fraction=.5, fraction_removed=.1)

    @pytest.mark.parametrize("clamper", [po.RangeClamper((0, 1)), po.RangeRemapper((0, 1)),
                                         'clamp2', 'clamp4'])
    @pytest.mark.parametrize("clamp_each_iter", [True, False])
    @pytest.mark.parametrize("cone_power", [1, 1/3])
    def test_metamer_clamper(self, clamper, clamp_each_iter, cone_power):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        if type(clamper) == str and clamper == 'clamp2':
            clamper = po.TwoMomentsClamper(im)
        elif type(clamper) == str and clamper == 'clamp4':
            clamper = po.FourMomentsClamper(im)
        rgc = po.simul.RetinalGanglionCells(.5, im.shape[2:], cone_power=cone_power)
        rgc = rgc.to(device)
        metamer = po.synth.Metamer(im, rgc)
        if cone_power == 1/3 and not clamp_each_iter:
            # these will fail because we'll end up outside the 0, 1 range
            with pytest.raises(IndexError):
                metamer.synthesize(max_iter=3, clamper=clamper, clamp_each_iter=clamp_each_iter)
        else:
            metamer.synthesize(max_iter=3, clamper=clamper, clamp_each_iter=clamp_each_iter)

    def test_metamer_no_clamper(self):
        im = plt.imread(op.join(DATA_DIR, 'nuts.pgm'))
        im = torch.tensor(im/255, dtype=dtype, device=device).unsqueeze(0).unsqueeze(0)
        rgc = po.simul.RetinalGanglionCells(.5, im.shape[2:], cone_power=1)
        rgc = rgc.to(device)
        metamer = po.synth.Metamer(im, rgc)
        metamer.synthesize(max_iter=3, clamper=None)
