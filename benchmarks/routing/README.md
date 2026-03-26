# Routing Benchmarks

Routing benchmarks verify vault-profile-aware note placement.

Current contents:

- `manifest.json` with profile-aware path-routing regression cases
- fixtures that check clear subtype placement under `obsidian_albert`
- guards against misrouting clear entities into the wrong `400 Entities/...` folder
- guards that ambiguous file-extracted fragments fall back to the profile default bucket

These cases are intended to protect the vault-adaptation layer while it is still being hardened.
