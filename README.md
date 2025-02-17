# Perovskite Automated Spin Coat Assembly Line (PASCAL)

## Motivation

PASCAL is an automated platform for spin coating and annealing thin films onto small (>2x2 cm) substrates, aimed af increasing experimental throughput in the pursuit of designing better perovskite solar cells. Perovskite solar cells are infinitely tunable, as they can be formed with combinations of nearly half of the periodic table, presenting the excitement of limitless possibilities and the curse of dimensionality. With PASCAL, we aim to increase our experimental search rate by orders of magnitude, enabling a more systematic and exhaustive approach toward exploring the vast compositional space of interest for solar cell design.

## Hardware

### CAD schematics of PASCAL

![top view](images/topview.png)
![front view](images/frontview.png)

### Liquid handler preparing precursor solution mixtures for a compositional search

![liquid handler preparing solutions for a composition spread](images/liquidhandling.gif)


### Liquid handler + spincoater working in conjunction to deposit solution onto substrate.

![spin coating one sample](images/spincoating.gif)

### Automated Full Sample Fabrication + Characterization Timelapse

https://github.com/fenning-research-group/PASCAL/assets/49666626/01028334-c0f0-4b86-ad78-245d9399b324

## Experimental Planning

- Computed material properties -> manifold embedding / dimensionality reduction into "behavior space"

![manifold embedding](images/manifold_redacted.png)

### Hardware Scheduling

![sample fabrication scheduling to parallelize sample processes while hitting target timings](images/hp_limited.png)

## Active Learning

### intra-run (narrow scope)

- bayesian approach to evaluating sample space
![bayesian posterior fit to experimental outcome](images/bayesian.png)

- update compositions of interest using in-line during experiment

![simulated bayesian optimization series](images/simulated_BO_search.png)

### inter-run (wide scope)

- bayesian approach with operator input (XRD, UV-Vis, etc)
- find covariances between composition/fabrication conditions
- point towards broader design philosophies in perovskite solar cells

## In-Line Characterization

- Widefield PL camera
![segmenting PL from wells](images/pl_segmentation.png)

- RGB Imaging for color determination
![PL wavelength determination with RGB cameras](images/WavelengthDeterminationwithNoise.png)

## Dependency
  - python=3.7.9=h26836e1_0

## Addons 

See our [fenningresearchgroup.com/https://github.com/fenning-research-group/PASCAL_TrainView
](https://github.com/fenning-research-group/PASCAL_TrainView)https://github.com/fenning-research-group/PASCAL_TrainView

and https://github.com/dnzckn/BO-PV repo's for additional capabilities
