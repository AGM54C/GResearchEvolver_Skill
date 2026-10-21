# MemTX — Code and Data

Code and data for the arXiv preprint MemTX: Transactional Belief Commit for
Stateful Agent Memory, by Xiaoyang Li, Yiqi Wang, Haohui Lu, Zhi Chen,
Mo Li, Pingan Song, and Taotao Cai. Preprint link to be added on
announcement.

The package holds the MemTX protocol, eight reimplemented baselines behind
one `MemoryManager` interface, the benchmark suites, and the result files
behind the paper's tables.

## Layout

    src/                core: schema, evaluator, runners, shared tool schemas
    src/memtx/          the MemTX protocol (state machine, commit validator,
                        conflict detector, dependency graph, ablation and
                        tier variants)
    src/baselines/      faithful baseline reimplementations + three augmented
                        single-graft variants + the official-MemState adapter
    scripts/            experiment drivers, case generators, stats, invariant
                        verifier, environment setup
    tests/              unit and property tests (pytest)
    data/               benchmark cases: realworld_scenarios/ (90),
                        realworld_hard/ (56), memtxbench_cases/ (172),
                        downstream_task/ (24)
    third_party/MemState/  authors' official implementation, vendored
                        unmodified (cross-check for our reimplementation)
    results/            CSVs behind the paper's tables; files carry
                        backend/model columns

## Setup

    pip install -r requirements.txt

The scripted suites and tests run CPU-only. The LLM path needs a served
model: open-weight backbones via vLLM 0.19.1 (`scripts/setup_env.sh`;
Mistral needs `--tool-call-parser mistral_fixed --tool-parser-plugin
scripts/mistral_fixed_tool_parser.py`), closed backbones via Azure OpenAI
credentials in `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` /
`AZURE_OPENAI_API_VERSION` / `AZURE_OPENAI_DEPLOYMENT` environment
variables. The official-MemState adapter needs `kuzu` (in requirements).

## Reproduction

    # scripted main experiment, all methods
    python scripts/run_experiments.py --cases data/realworld_scenarios

    # scripted ablations (10 single-component variants, both suites)
    python scripts/run_ablation.py --cases data/realworld_scenarios
    python scripts/run_ablation.py --cases data/realworld_hard

    # LLM path (per backbone; add --cases data/realworld_hard for hard56)
    python scripts/run_llm_experiment.py --backend vllm --model qwen3-8b \
        --temperature 0 --results-dir results/llm_repro

    # risk-tier pricing arms
    python scripts/run_llm_experiment.py --backend vllm --model qwen3-8b \
        --temperature 0 --methods memtx --honor-case-risk \
        --results-dir results/tier_repro
    #   matured store: --methods memtx_matured --honor-case-risk

    # isolation sweep, threshold sensitivity, downstream harm pipeline
    python scripts/run_isolation_sweep.py
    python scripts/run_threshold_sweep.py
    python scripts/run_downstream.py

    # paired stats (bootstrap CI + exact McNemar) over any per-case CSV
    python scripts/aggregate_stats.py <per_case.csv> --ref memtx

    # multiple-comparison and clustering robustness audit
    python scripts/stats_correction_audit.py

    # machine-checked protocol invariants
    python scripts/verify_invariants.py

    # tests (tau2 adapter test skips without the external tau2-bench tree)
    python -m pytest tests -q

Scripted runs are deterministic: mock tools return fixed values for fixed
arguments, and grading is pure-rule over case-declared ground truth. LLM
runs at temperature zero; result files never overwrite another model's
(per-model filenames).

## Citation

    @misc{li2026memtx,
      title={MemTX: Transactional Belief Commit for Stateful Agent Memory},
      author={Li, Xiaoyang and Wang, Yiqi and Lu, Haohui and Chen, Zhi
              and Li, Mo and Song, Pingan and Cai, Taotao},
      year={2026},
      note={arXiv preprint}
    }
