---
title: 'Plenoptic.py: Synthesizing model-optimized visual stimuli'
tags:
  - Python
  - PyTorch
  - neural networks
  - computational neuroscience
  - image synthesis
authors:
  - name: Kathryn Bonnen
    orcid: 0000-0002-9210-8275
    affiliation: 1, 2
  - name: William F. Broderick
    orcid: 0000-0002-8999-9003
    affiliation: 1
  - name: Lyndon R. Duong
    orcid: 0000-0003-0575-1033
    affiliation: 1
  - name: Pierre-Etienne Fiquet
    orcid: 0000-0002-8301-2220
    affiliation: 1
  - name: Nikhil Parthasarathy
    orcid: 0000-0003-2572-6492
    affiliation: 1
  - name: Xinyuan Zhao
    orcid: 0000-0003-2572-6492
    affiliation: 1
  - name: Thomas E. Yerxa
    orcid: 0000-0003-2572-6492
    affiliation: 1
  - name: Eero P. Simoncelli
    orcid: 000-0002-1206-527X
    affiliation: 1, 2
affiliations:
 - name: Center for Neural Science, New York University, New York, NY, USA
   index: 1
 - name: Center for Computational Neuroscience, Flatiron Institute, New York, NY, USA
   index: 2
date: January 2023
bibliography: references.bib
---

# Summary

In sensory perception and neuroscience, new computational models are most often tested and compared in terms of their ability to fit existing data sets.
However, experimental data are inherently limited in size, quality, and type, and complex models often saturate their explainable variance.
Moreover, it is often difficult to use models to guide the development of future experiments.
Here, building on ideas for optimal experimental stimulus selection  (e.g., QUEST, Watson and Pelli, 1983), we present "Plenoptic", a python software library for generating visual stimuli optimized for testing or comparing models.
Plenoptic provides a unified framework containing four previously-published synthesis methods -- model metamers (Freeman and Simoncelli, 2011), Maximum Differentiation (MAD) competition (Wang and Simoncelli, 2008), eigen-distortions (Berardino et al. 2017), and representational geodesics (Hénaff and Simoncelli, 2015) -- each of which offers visualization of model representations, and generation of images that can be used to experimentally test alignment with the human visual system.
Plenoptic leverages modern machine-learning methods to enable application of these synthesis methods to any computational model that satisfies a small set of common requirements.
The most important of these is that the model must be image-computable, implemented in PyTorch, and end-to-end differentiable.
The package includes examples of several low- and mid-level visual models, as well as a set of perceptual quality metrics.
Plenoptic is open source, tested, documented, and extensible, allowing the broader research community to contribute new examples and methods.
In summary, Plenoptic leverages machine learning tools to tighten the scientific hypothesis-testing loop, facilitating investigation of human visual representations.

# Acknowledgements

All authors contributed equally to this work; and names are listed alphabetically.
EPS and KB were funded by Simons Institute.

For a quick reference, the following citation commands can be used:

- `@author:2001`  ->  "Author et al. (2001)"
- `[@author:2001]` -> "(Author et al., 2001)"
- `[@author1:2001; @author2:2001]` -> "(Author1 et al., 2001; Author2 et al., 2002)"

# References

@berardino_eigen-distortions_2017
@henaff_geodesics_2015
@simoncelli_steerable_1995
@freeman_metamers_2011
@wang_maximum_2008
@paszke_pytorch_2019
@portilla_parametric_2000