# Retrieval QA Benchmarks

This suite checks whether the vault can answer source-grounded retrieval questions after ingestion.

Current cases focus on deterministic mention retrieval from representative file inputs.

Each question asserts:

- the expected canonical note appears in the retrieved top matches
- the retrieved answer includes a citation to the expected source block
- the cited source path matches the expected source slug fragment

Run the suite with:

```bash
python3 main.py benchmark-run --manifest benchmarks/retrieval/manifest.json
```

You can also run the same question format directly against an existing vault with:

```bash
python3 main.py qa-run --vault /path/to/vault --questions /path/to/questions.json
```
