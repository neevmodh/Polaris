# Sources and reuse

Polaris Task3 is a new integrated application. Original source repositories and their
licenses are retained, unmodified, under `references/`. No ownership of upstream
models, algorithms, datasets or dashboards is claimed.

| Repository | Pinned revision | License | Actual use |
|---|---|---|---|
| [AwasthiAshutosh/TerraVision](https://github.com/AwasthiAshutosh/TerraVision) | `a204f8420cdbfc0138b9b34b7666d8ce2b1b221b` | MIT, © 2026 Ashutosh Awasthi | SCL masking approach, NDVI difference screening and dashboard workflow adapted. Synthetic fallback was not ported. We exclude SCL 7, apply radiometric offsets, require baseline vegetation and filter small patches. |
| [NightSongs/Forest-CD](https://github.com/NightSongs/Forest-CD) | `48e5c1cc3374a67c8db3cab74c4ebaba18e34848` | MIT, © 2022 NightSongs | Research reference for paired-image forest change detection. Included source is available for extension; its research network is not executed or claimed as our trained model. |
| [Iulia-plesu/lake-detection-water-quality](https://github.com/Iulia-plesu/lake-detection-water-quality) | `785413e072c8d0c792a84920b32c8631c23f0d12` | Apache-2.0 | Original `models.py` U-Net architecture is loaded by the water adapter. Upstream pretrained weights are verified against its Git LFS SHA256. Band order/min-max normalization are adapted from `unet_predict.py`. We add overlap-tiled CPU inference, safe state-dictionary loading and SCL exclusion; no upstream oil-pollution or water-safety claim is adopted. |
| [RAJohansen/waterquality](https://github.com/RAJohansen/waterquality) | `b34598325315eeebdf268e33c53a967a8884df5f` | MIT, © 2020 Richard Johansen, Jakub Nowosad | The `MM12NDCIalt` normalized red-edge/red form and `TurbBe16GreenPlusRedBothOverViolet` ratio are ported to NumPy using nearby Sentinel-2 bands. The wavelength approximation and lack of local calibration are explicit. R package itself is not a runtime dependency. |

The Python adapters and ports are visibly documented in `monitor/indices.py`,
`monitor/scenes.py`, and `monitor/water_model.py`. All modifications described above
are Polaris additions; upstream source trees remain unchanged except that model
files in the cloned lake repository retain their Git LFS pointers.

## Data and scientific references

- Copernicus Sentinel-2 Collection 1 Level 2A imagery, accessed from the public
  [Element 84 Earth Search catalog](https://github.com/Element84/earth-search).
  Copernicus Sentinel data are free/open under the Sentinel data terms.
  STAC metadata, exact image IDs, dates, asset URLs and scale/offset values are cached.
- Hansen et al., *High-Resolution Global Maps of 21st-Century Forest Cover Change*,
  Science 342 (2013), 850–853. DOI: `10.1126/science.1244693`.
  [GFC 2024 v1.12](https://storage.googleapis.com/earthenginepartners-hansen/GFC-2024-v1.12/download.html),
  CC BY 4.0. Used as a satellite-derived reference map, not independent field truth.
- Water spectral ratios follow the upstream algorithm references in
  `references/waterquality/R/algorithms.R`; band approximations are screening proxies.
- U-Net checkpoint: `124243147` bytes, SHA256
  `60ba90b759dc90cc935bb127782307bdaa4e9059bf5b7b62f403e9e584c7d1f4`.

See the original licenses in each reference directory. Attribution should remain
in any redistributed submission. The original papers and datasets should also be
credited in the presentation.
