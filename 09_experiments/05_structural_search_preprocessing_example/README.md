# Structural search preprocessing example

This experiment is isolated from the Exhibition output.

- Source: `ice_crystal_03`, `patch_49.jpg`
- Preprocessing comparison:
  - original
  - strong black/white contrast enhancement
  - structure enhancement (local contrast plus restrained contour overlay)
- Search experiment:
  - iNaturalist + NASA candidate APIs
  - contrast and structure generate independent language expansions
  - each branch requests and ranks its own candidate pool
  - CLIP semantic gate with branch-matched HOG as a secondary weighted score
  - the trial result files were cleared after the search policy was approved

The official `ice_crystal_03` manifest and saved search results are unchanged.
The dual search profile is now the search-worker default:

```text
--patch-transform dual --ranking-mode structure_fusion
```

`ice_crystal_03` has now been regenerated using the approved dual-search
policy.

The Exhibition default selects six representative patches. Each patch keeps
five contrast results and five structure results:

```text
6 patches × 2 branches × 5 results = 60 saved images
```

The webpage presents one five-image branch at a time.
