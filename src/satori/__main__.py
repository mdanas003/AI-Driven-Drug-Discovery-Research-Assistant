"""Command line entry point.

    python -m satori describe "<SMILES>" ...      # one or more molecules
    python -m satori screen library.csv [options] # a whole CSV library
    python -m satori fetch-chembl CHEMBL203       # real data for one target
    python -m satori similar GEFITINIB lib.csv    # nearest neighbours
    python -m satori cluster lib.csv              # group into series
    python -m satori train lib.csv                # predict potency, scored two ways
    python -m satori predict model.joblib "<SMILES>"
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np
import requests

from satori import benchmark as bench
from satori.features import featurize
from satori.labels import (
    DEFAULT_MAX_SPREAD,
    DEFAULT_MIN_MEASUREMENTS,
    WEIGHT_SCHEMES,
    confident_indices,
    quality_of,
    restrict,
    weights,
)

from satori.chembl import DEFAULT_ACTIVE_THRESHOLD, build_dataset
from satori.library import load_csv, load_table, rank, save_csv, screen
from satori.model import (
    DEFAULT_REPEATS,
    DEFAULT_TEST_FRACTION,
    DEFAULT_TREES,
    RepeatedScores,
    Split,
    cluster_split,
    evaluate,
    evaluate_repeated,
    features,
    random_forest,
    random_split,
)
from satori.molecule import canonical_smiles, parse_smiles, strip_salts
from satori.multitask import (
    arms_for,
    audit,
    build_pool,
    with_task_feature,
)
from satori.similarity import (
    DEFAULT_CUTOFF,
    cluster,
    fingerprint,
    fingerprint_library,
    fingerprint_of,
    most_similar,
)

# Longer results are summarized; use --out to get every row.
MAX_PRINTED_ROWS = 20
from satori.molecule import describe, lipinski, parse_smiles

EXAMPLES = {
    "aspirin": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    "ibuprofen": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
    "cyclosporine": (
        "CCC1C(=O)N(CC(=O)N(C(C(=O)NC(C(=O)N(C(C(=O)NC(C(=O)NC(C(=O)N(C(C(=O)"
        "N(C(C(=O)N(C(C(=O)N(C(C(=O)N1)C(C(C)CC=CC)O)C)C(C)C)C)CC(C)C)C)CC(C)C)"
        "C)C)C)CC(C)C)C)C(C)C)CC(C)C)C)C"
    ),
}


def report(name: str, smiles: str) -> bool:
    """Print one molecule's properties and verdict. Returns False on bad input."""
    print(f"\n== {name} ==")
    try:
        mol = parse_smiles(smiles)
    except ValueError as err:
        print(f"  error: {err}")
        return False

    props = describe(mol)
    for key, value in props.items():
        print(f"  {key:<18} {value}")

    passes, violations = lipinski(props)
    print(f"  {'drug-like?':<18} {'PASS' if passes else 'FAIL'} (Lipinski Rule of Five)")
    for v in violations:
        print(f"    - violates {v}")
    return True


def cmd_describe(args: argparse.Namespace) -> int:
    molecules = {s: s for s in args.smiles} if args.smiles else EXAMPLES
    ok = [report(name, smiles) for name, smiles in molecules.items()]
    return 0 if all(ok) else 1


def cmd_screen(args: argparse.Namespace) -> int:
    try:
        rows = load_csv(args.csv)
    except (OSError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    result = screen(rows)
    ranked = rank(result.compounds, drug_like_only=args.drug_like, top=args.top)

    print(f"Read {len(rows)} rows from {args.csv}")
    print(f"  valid and unique: {len(result.compounds)}")
    for name, reason in result.invalid:
        print(f"  skipped invalid:  {name} ({reason})")
    for name, original in result.duplicates:
        print(f"  skipped duplicate: {name} (same molecule as {original})")

    print(f"\n{'rank':>4}  {'name':<16} {'QED':>5}  {'MW':>8}  {'logP':>5}  Lipinski")
    for i, c in enumerate(ranked[:MAX_PRINTED_ROWS], start=1):
        p = c.props
        verdict = "PASS" if c.drug_like else "FAIL"
        print(
            f"{i:>4}  {c.name:<16} {p['qed']:>5.3f}  {p['molecular_weight']:>8.2f}"
            f"  {p['logp']:>5.2f}  {verdict}"
        )
    if len(ranked) > MAX_PRINTED_ROWS:
        print(f"  ... and {len(ranked) - MAX_PRINTED_ROWS} more (use --out to save them all)")

    if args.out:
        if not ranked:
            print("\nNothing passed the filters, so no file was written.")
            return 1
        save_csv(ranked, args.out)
        print(f"\nSaved {len(ranked)} compounds to {args.out}")
    return 0


def cmd_fetch_chembl(args: argparse.Namespace) -> int:
    def progress(done: int, total: int) -> None:
        print(f"\r  downloaded {done:,} / {total:,} measurements", end="", flush=True)

    print(f"Fetching {args.type} data for {args.target} from ChEMBL...")
    try:
        summary = build_dataset(
            args.target,
            args.type,
            Path(args.out_dir),
            active_threshold=args.threshold,
            refresh=args.refresh,
            progress=progress,
        )
    except (requests.RequestException, RuntimeError, ValueError) as err:
        print(f"\nerror: {err}", file=sys.stderr)
        return 1

    source = summary["source"]
    print(f"\n\n{source['target_name']} ({source['target_chembl_id']}), {source['chembl_release']}")
    print(f"  downloaded {source['downloaded_at']}")
    print(f"  raw measurements:  {summary['raw_measurements']:>7,}")
    for reason, count in summary["dropped"].items():
        print(f"    dropped {count:>7,}  {reason}")
    print(f"  kept measurements: {summary['kept_measurements']:>7,}")

    threshold = summary["active_threshold_pchembl"]
    for label, part in (("normal (wild-type)", "wild_type"), ("mutant forms", "mutant")):
        counts = summary[part]
        if not counts["molecules"]:
            continue
        share = counts["actives"] / counts["molecules"]
        print(f"\n  {label}: {counts['molecules']:,} molecules")
        print(f"    active (pChEMBL >= {threshold}): {counts['actives']:,} ({share:.0%})")
        variants = counts.get("variants")
        if variants:
            top = ", ".join(f"{name} ({n:,})" for name, n in list(variants.items())[:5])
            print(f"    {len(variants)} distinct variants, most measured: {top}")

    print()
    for path in summary["files"].values():
        print(f"Saved {path}")
    print(f"Saved {Path(args.out_dir) / f'{args.target}_{args.type}'}.json (provenance)")
    return 0


def load_library(path: str) -> tuple[list[dict], list, bool]:
    """Read a library CSV and fingerprint it, reporting what was skipped."""
    rows, fps, skipped = fingerprint_library(load_table(path))
    print(f"Library: {len(rows):,} molecules from {path}")
    if skipped:
        print(f"  skipped {len(skipped)} unreadable structure(s): {', '.join(skipped[:5])}")
    return rows, fps, "pchembl" in (rows[0] if rows else {})


def potency_column(row: dict, has_potency: bool) -> str:
    """The potency cell for a results table, blank if the library has none."""
    if not has_potency:
        return ""
    label = row.get("variant", "")
    return f"  {row['pchembl']:>5}  {label}"


def standard_form(smiles: str) -> str:
    """One canonical spelling, salts removed, for comparing structures."""
    return canonical_smiles(strip_salts(parse_smiles(smiles)))


def resolve_query(query: str, rows: list[dict]) -> tuple[int | None, str]:
    """Interpret the query as a SMILES string, or as a name in the library."""
    try:
        return None, standard_form(query)
    except ValueError:
        wanted = query.strip().lower()
        for i, row in enumerate(rows):
            if wanted in (row["name"].lower(), row.get("pref_name", "").lower()):
                return i, standard_form(row["smiles"])
        raise ValueError(
            f"{query!r} is neither a valid SMILES string nor a name in the library"
        ) from None


def cmd_similar(args: argparse.Namespace) -> int:
    try:
        rows, fps, has_potency = load_library(args.csv)
        in_library, smiles = resolve_query(args.query, rows)
    except (OSError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    if in_library is None:
        print(f"Query: {smiles}")
    else:
        found = rows[in_library]
        label = found.get("pref_name") or found["name"]
        print(f"Query: {label} ({found['name']}) found in the library")
    query_fp = fingerprint(strip_salts(parse_smiles(smiles)))

    # The query's own structure is not a neighbour of itself. It can appear
    # in several rows at once: the mutant file holds one row per variant.
    hits = []
    for hit in most_similar(query_fp, fps, top=args.top * 3 + 20, minimum=args.min):
        if hit.similarity == 1.0 and standard_form(rows[hit.index]["smiles"]) == smiles:
            continue
        hits.append(hit)
        if len(hits) == args.top:
            break
    if not hits:
        print(f"\nNothing in the library reaches similarity {args.min}.")
        return 0

    header = f"\n{'rank':>4}  {'similarity':>10}  {'name':<16} {'label':<22}"
    print(header + ("  pChEMBL  variant" if has_potency else ""))
    for i, hit in enumerate(hits, start=1):
        row = rows[hit.index]
        label = (row.get("pref_name") or "")[:22]
        print(
            f"{i:>4}  {hit.similarity:>10.3f}  {row['name']:<16} {label:<22}"
            f"{potency_column(row, has_potency)}"
        )

    if has_potency:
        hit_median = statistics.median(float(rows[h.index]["pchembl"]) for h in hits)
        all_median = statistics.median(float(r["pchembl"]) for r in rows)
        difference = hit_median - all_median
        print(
            f"\nMedian pChEMBL of these {len(hits)} neighbours: {hit_median:.2f}"
            f"  (whole library: {all_median:.2f}, difference {difference:+.2f})"
        )
        if difference > 0:
            print("Neighbours more potent than the library: the similarity principle holding.")
        else:
            print("Neighbours no more potent than the library: the principle does not always hold.")
    return 0


def cmd_cluster(args: argparse.Namespace) -> int:
    try:
        rows, fps, has_potency = load_library(args.csv)
    except (OSError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    if not rows:
        print("error: the library is empty", file=sys.stderr)
        return 1

    # Let the most potent molecules become cluster centres.
    order = None
    if has_potency:
        order = sorted(range(len(rows)), key=lambda i: -float(rows[i]["pchembl"]))

    print(f"Clustering at Tanimoto >= {args.cutoff} ...")
    clusters = cluster(fps, cutoff=args.cutoff, order=order)
    singletons = sum(1 for c in clusters if len(c) == 1)
    print(f"  {len(clusters):,} clusters")
    print(f"  {singletons:,} of them a single molecule on its own")
    print(f"  largest holds {len(clusters[0]):,} molecules")

    header = f"\n{'cluster':>7}  {'size':>6}  {'centre':<16} {'label':<22}"
    print(header + ("  pChEMBL  variant" if has_potency else ""))
    for i, group in enumerate(clusters[: args.top], start=1):
        row = rows[group.centre]
        label = (row.get("pref_name") or "")[:22]
        print(
            f"{i:>7}  {len(group):>6,}  {row['name']:<16} {label:<22}"
            f"{potency_column(row, has_potency)}"
        )
    if len(clusters) > args.top:
        print(f"  ... and {len(clusters) - args.top:,} more clusters")
    return 0


def print_scores(scores: RepeatedScores, explanation: str) -> None:
    first = scores.runs[0]
    print(f"\n  {scores.split} split  ({explanation})")
    print(
        f"    {scores.repeats} repeats, each training on {first.n_train:,}"
        f" and testing on {first.n_test:,}"
    )
    for label, metric in (
        ("R2 (variation explained)", scores.r2),
        ("MAE (average error)", scores.mae),
        ("Spearman (ranking)", scores.spearman),
        ("always guess the average", scores.baseline_mae),
    ):
        print(f"    {label:<26} {metric}   (lowest {metric.low}, highest {metric.high})")
    if not scores.beats_baseline:
        print("    -> some repeats were no better than guessing the average")


def scores_as_dict(scores: RepeatedScores) -> dict:
    """A saved model's scores, flat enough to read without importing Satori."""
    return {
        "split": scores.split,
        "repeats": scores.repeats,
        **{name: vars(getattr(scores, name)) for name in ("r2", "mae", "spearman", "baseline_mae")},
    }


def cmd_train(args: argparse.Namespace) -> int:
    try:
        rows, fps, _ = load_library(args.csv)
        if args.column not in (rows[0] if rows else {}):
            raise ValueError(f"{args.csv}: no '{args.column}' column to learn from")
        values = np.array([float(row[args.column]) for row in rows])
    except (OSError, ValueError, KeyError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    x = features(fps)
    print(f"  learning {args.column} from {x.shape[1]:,} fingerprint bits with {args.model}")
    model_for = (
        (lambda seed: random_forest(args.trees, seed))
        if args.model == "random_forest"
        else bench.MODELS[args.model]
    )

    print(f"\nClustering at Tanimoto >= {args.cutoff} to build the honest split ...")
    clusters = cluster(fps, cutoff=args.cutoff)
    print(f"  {len(clusters):,} chemical series among {len(rows):,} molecules")

    split_makers = {
        "random": lambda seed: random_split(len(rows), args.test_fraction, seed),
        "cluster": lambda seed: cluster_split(clusters, args.test_fraction, seed),
    }
    results = {}
    for name, make_split in split_makers.items():
        print(f"\nTraining {args.model} x {args.repeats} repeats, {name} split ...")
        forest, scores = evaluate_repeated(
            x,
            values,
            make_split,
            repeats=args.repeats,
            model_for=model_for,
            seed=args.seed,
            on_run=lambda i, s: print(f"  repeat {i + 1}: R2 {s.r2:.3f}, MAE {s.mae:.3f}"),
        )
        results[name] = (forest, scores)
        print_scores(scores, make_split(args.seed).explanation)

    optimistic, honest = results["random"][1], results["cluster"][1]
    gap = optimistic.r2.mean - honest.r2.mean
    # A gap smaller than the spread of the measurements is not a finding.
    noise = max(optimistic.r2.sd, honest.r2.sd)
    print(f"\nThe random split flatters this model by {gap:.3f} R2 on average.")
    if gap <= noise:
        print(
            f"That gap is within the run-to-run spread ({noise:.3f}),"
            " so these two splits are not measurably different here."
        )
    else:
        print(f"That is larger than the run-to-run spread ({noise:.3f}), so the gap is real.")
    print("Only the cluster number says anything about a series you have not made yet.")

    if args.save:
        import joblib

        path = Path(args.save)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Keep the honest scores with the model, so it can never be quoted
        # without them.
        joblib.dump(
            {
                "forest": results["cluster"][0],
                "predicts": args.column,
                "trained_on": str(args.csv),
                "molecules": len(rows),
                "model": args.model,
                "cluster_cutoff": args.cutoff,
                "scores": {
                    "random": scores_as_dict(optimistic),
                    "cluster": scores_as_dict(honest),
                },
            },
            path,
        )
        print(f"\nSaved the cluster-split model to {path}")
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    import joblib

    try:
        bundle = joblib.load(args.model)
    except (OSError, KeyError) as err:
        print(f"error: cannot read model {args.model}: {err}", file=sys.stderr)
        return 1

    honest = bundle["scores"]["cluster"]
    mae, r2 = honest["mae"], honest["r2"]
    print(f"Model predicts {bundle['predicts']}, trained on {bundle['molecules']:,} molecules")
    print(
        f"  over {honest['repeats']} repeats on unseen chemical series it was out by"
        f" {mae['mean']:.2f} +/- {mae['sd']:.2f} on average"
        f" (R2 {r2['mean']:.3f} +/- {r2['sd']:.3f})"
    )
    print("  read every number below with that in mind")

    ok = True
    for smiles in args.smiles:
        try:
            prediction = bundle["forest"].predict(features([fingerprint_of(smiles)]))[0]
        except ValueError as err:
            print(f"\n  {smiles}\n    error: {err}")
            ok = False
            continue
        print(f"\n  {smiles}")
        print(f"    predicted {bundle['predicts']} = {prediction:.2f} +/- {mae['mean']:.2f}")
    return 0 if ok else 1


def load_molecules(path: str, column: str) -> tuple[list, np.ndarray, list]:
    """Read a library as RDKit molecules plus the values to learn."""
    rows = load_table(path)
    if rows and column not in rows[0]:
        raise ValueError(f"{path}: no '{column}' column to learn from")

    mols, values, skipped = [], [], []
    for row in rows:
        try:
            mols.append(strip_salts(parse_smiles(row["smiles"])))
            values.append(float(row[column]))
        except ValueError:
            skipped.append(row["name"])
    if not mols:
        raise ValueError(f"{path}: no readable molecules")
    return mols, np.array(values), skipped


def data_agreement(csv_path: str) -> dict | None:
    """The resolution limit recorded by `fetch-chembl` beside this library."""
    path = Path(csv_path)
    for suffix in ("_wild_type", "_mutant", ""):
        if suffix and not path.stem.endswith(suffix):
            continue
        sibling = path.with_name(path.stem.removesuffix(suffix) + ".json")
        if sibling.exists():
            try:
                return json.loads(sibling.read_text(encoding="utf-8"))["measurement_agreement"]
            except (KeyError, ValueError):
                return None
    return None


def cmd_benchmark(args: argparse.Namespace) -> int:
    try:
        mols, values, skipped = load_molecules(args.csv, args.column)
    except (OSError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"Library: {len(mols):,} molecules from {args.csv}")
    if skipped:
        print(f"  skipped {len(skipped)} unusable row(s): {', '.join(skipped[:5])}")

    contestants = bench.DEFAULT_CONTESTANTS
    if args.only:
        contestants = [(m, f) for m, f in contestants if m in args.only]
        if not contestants:
            print(f"error: no contestants named {args.only}", file=sys.stderr)
            return 1

    print(f"\nClustering at Tanimoto >= {args.cutoff} for the honest split ...")
    fps = [fingerprint(mol) for mol in mols]
    clusters = cluster(fps, cutoff=args.cutoff)
    print(f"  {len(clusters):,} chemical series among {len(mols):,} molecules")

    print("\nBuilding representations ...")
    tables = {}
    for name in sorted({feature for _, feature in contestants}):
        tables[name] = featurize(name, mols)
        print(f"  {name:<26} {tables[name].shape[1]:>5,} features")

    results = bench.run(
        tables,
        values,
        lambda seed: cluster_split(clusters, args.test_fraction, seed),
        contestants=contestants,
        repeats=args.repeats,
        seed=args.seed,
        on_start=lambda m, f: print(f"\nTraining {m} on {f}, {args.repeats} repeats ...", flush=True),
        on_finish=lambda r: print(
            f"  {'failed: ' + r.error if r.error else f'R2 {r.scores.r2}'}"
            f"   [{r.seconds:.0f}s]"
        ),
    )

    print(f"\n{'model':<18} {'features':<26} {'R2':>16} {'MAE':>16} {'Spearman':>8} {'top 10%':>8}")
    for result in results.ranked:
        s = result.scores
        print(
            f"{result.model:<18} {result.features:<26} {str(s.r2):>16} {str(s.mae):>16}"
            f" {s.spearman.mean:>8.3f} {s.top_hit_rate.mean:>8.2f}"
        )
    for result in (r for r in results.results if r.error):
        print(f"{result.model:<18} {result.features:<26} failed: {result.error}")

    if not results.ranked:
        print("\nerror: every contestant failed", file=sys.stderr)
        return 1

    best = results.ranked[0]
    tied = [r for r in results.ranked[1:] if results.ties_with_best(r)]
    print(f"\nBest honest R2: {best.model} on {best.features} ({best.scores.r2}).")
    if tied:
        names = ", ".join(f"{r.model} on {r.features}" for r in tied)
        print(f"Tied with it, within the run-to-run spread: {names}.")
        print("A difference smaller than the spread is not a result; prefer the simpler model.")
    print(
        f"Picking the model's top 10%, {best.scores.top_hit_rate.mean:.0%} are genuinely"
        " among the most potent (picking at random would give 10%)."
    )

    agreement = data_agreement(args.csv)
    if agreement:
        limit = agreement["mean_difference"]
        print(
            f"\nThe data's own limit: two real measurements of the same molecule differ by"
            f" {limit:.2f} on average."
        )
        if best.scores.mae.mean <= limit:
            print(
                f"The best model's error ({best.scores.mae.mean:.2f}) is already inside that."
                " Absolute accuracy cannot improve further on these labels; better"
                " ranking and better labels are where the headroom is."
            )
    return 0


def cmd_labels(args: argparse.Namespace) -> int:
    """Measure how much of the error is the data's rather than the model's."""
    try:
        rows = load_table(args.csv)
        mols, values, skipped = load_molecules(args.csv, args.column)
        if "n_measurements" not in (rows[0] if rows else {}):
            raise ValueError(f"{args.csv}: no 'n_measurements' column to judge labels by")
        rows = [row for row in rows if row["name"] not in set(skipped)]
    except (OSError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    qualities = [quality_of(row) for row in rows]
    confident = confident_indices(rows, args.min_measurements, args.max_spread)
    print(f"Library: {len(rows):,} molecules from {args.csv}")
    print(f"  measured once only:      {sum(q.n_measurements == 1 for q in qualities):>7,}")
    print(f"  measured more than once: {sum(q.n_measurements > 1 for q in qualities):>7,}")
    print(
        f"  confident (>= {args.min_measurements} measurements, spread <= {args.max_spread}):"
        f" {len(confident):>7,}"
    )
    if len(confident) < 50:
        print("error: too few confident labels to measure anything", file=sys.stderr)
        return 1

    x = featurize(args.features, mols)
    fps = [fingerprint(mol) for mol in mols]
    clusters = cluster(fps, cutoff=args.cutoff)
    print(f"  {len(clusters):,} chemical series, clustered at {args.cutoff}")

    confident_set = set(confident)
    model_for = bench.MODELS[args.model]
    everything = set(range(len(rows)))

    def measure(name: str, train_allowed: set[int], test_allowed: set[int], weighting: str):
        sample_weight = None if weighting == "equal" else weights(rows, weighting)
        _, scores = evaluate_repeated(  # may raise ValueError on an empty side
            x,
            values,
            lambda seed: restrict(
                cluster_split(clusters, args.test_fraction, seed),
                train_allowed=None if train_allowed == everything else train_allowed,
                test_allowed=None if test_allowed == everything else test_allowed,
            ),
            repeats=args.repeats,
            model_for=model_for,
            seed=args.seed,
            sample_weight=sample_weight,
        )
        print(
            f"  {name:<34} R2 {str(scores.r2):>16}  MAE {str(scores.mae):>16}"
            f"  top10% {scores.top_hit_rate.mean:.2f}"
        )
        return scores

    print(f"\nUsing {args.model} on {args.features}, {args.repeats} repeats each.")

    try:
        print("\nExperiment 1: does a cleaner test set give a truer score?")
        print("  (identical training; only what we score on changes)")
        on_all = measure("scored on every label", everything, everything, "equal")
        on_confident = measure(
            "scored on confident labels only", everything, confident_set, "equal"
        )

        print("\nExperiment 2: does trusting better labels more help the model?")
        print("  (identical confident test set; only the training changes)")
        trials = {"all labels, unweighted": ("equal", everything)}
        for scheme in args.schemes:
            if scheme != "equal":
                trials[f"all labels, weighted by {scheme}"] = (scheme, everything)
        trials["confident labels only"] = ("equal", confident_set)

        results = {
            name: measure(name, train_allowed, confident_set, scheme)
            for name, (scheme, train_allowed) in trials.items()
        }
    except ValueError as err:
        print(f"\nerror: {err}", file=sys.stderr)
        print("Try a smaller --test-fraction, or a tighter --cutoff.", file=sys.stderr)
        return 1

    difference = on_all.mae.mean - on_confident.mae.mean
    noise = max(on_all.mae.sd, on_confident.mae.sd)

    print("\nWhat this says:")
    if difference > noise:
        print(
            f"  Scoring on confident labels cuts the error by {difference:.3f} MAE,"
            f" more than the run-to-run spread ({noise:.3f})."
        )
        print(
            f"  So roughly {difference:.2f} of the {on_all.mae.mean:.2f} error was the data's,"
            f" not the model's. Against clean labels the model is out by"
            f" {on_confident.mae.mean:.2f}."
        )
    else:
        print(
            f"  Scoring on confident labels changes the error by only {difference:+.3f} MAE,"
            f" within the spread ({noise:.3f}): label noise is not what limits this model."
        )

    best = min(results.items(), key=lambda item: item[1].mae.mean)
    baseline = results["all labels, unweighted"]
    gain = baseline.mae.mean - best[1].mae.mean
    weight_noise = max(baseline.mae.sd, best[1].mae.sd)
    if gain > weight_noise:
        print(f"  Best training strategy: {best[0]} ({gain:.3f} MAE better than unweighted).")
    else:
        print(
            f"  No training strategy beat plain unweighted labels by more than the"
            f" spread ({weight_noise:.3f}). Weighting is not worth the complexity here."
        )
    print(
        f"  Only {len(confident):,} of {len(rows):,} molecules have a label we can check,"
        " so the ceiling itself is measured on thin evidence."
    )
    return 0


def cmd_multitask(args: argparse.Namespace) -> int:
    """Does data from related proteins help predict the primary one?"""
    try:
        tables = {Path(args.csv).stem: load_table(args.csv)}
        for extra in args.also or []:
            tables[Path(extra).stem] = load_table(extra)
        pool = build_pool(tables, args.primary, args.column)
    except (OSError, ValueError, KeyError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"Pool: {len(pool):,} measurements across {len(pool.task_names)} proteins")
    for name in pool.task_names[:8]:
        marker = "  <- judged on this" if name == args.primary else ""
        print(f"  {name:<24} {len(pool.indices_of(name)):>6,} rows{marker}")
    if len(pool.task_names) > 8:
        print(f"  ... and {len(pool.task_names) - 8} more proteins")

    try:
        mols = [strip_salts(parse_smiles(s)) for s in pool.smiles]
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    fps = [fingerprint(mol) for mol in mols]
    x = with_task_feature(featurize(args.features, mols), pool)
    print(f"  {x.shape[1]:,} features: {x.shape[1] - len(pool.task_names):,} structural"
          f" + {len(pool.task_names)} saying which protein")

    primary_rows = pool.indices_of(args.primary)
    clusters = cluster([fps[i] for i in primary_rows], cutoff=args.cutoff)
    print(f"\n{len(clusters):,} chemical series among the {len(primary_rows):,} primary molecules")

    runs: dict[str, list] = {"single_task": [], "multi_task": []}
    audits = []
    for repeat in range(args.repeats):
        seed = args.seed + repeat
        series_split = cluster_split(clusters, args.test_fraction, seed)
        # Cluster indices count primary molecules; the pool counts every row.
        in_pool = Split(
            "primary",
            [primary_rows[i] for i in series_split.train],
            [primary_rows[i] for i in series_split.test],
            series_split.explanation,
        )
        single, multi = arms_for(pool, fps, in_pool, args.cutoff)

        for arm in (single, multi):
            report = audit(fps, arm.train, arm.test, args.cutoff)
            audits.append((arm.name, report))
            if not report.clean:
                print(
                    f"\nerror: {arm.name} leaked on repeat {repeat + 1}:"
                    f" {report.offenders} training molecules within {args.cutoff}"
                    f" of a test molecule (worst {report.worst_similarity})",
                    file=sys.stderr,
                )
                return 1
            _, scores = evaluate(x, pool.values, arm, bench.MODELS[args.model], seed)
            runs[arm.name].append(scores)

        print(
            f"  repeat {repeat + 1}: single {len(single.train):,} rows ->"
            f" R2 {runs['single_task'][-1].r2:.3f}   multi {len(multi.train):,} rows ->"
            f" R2 {runs['multi_task'][-1].r2:.3f}"
        )

    worst = max(report.worst_similarity for _, report in audits)
    print(
        f"\nLeakage audit passed on all {len(audits)} training sets:"
        f" closest any training molecule came to a test molecule was {worst}"
        f" (limit {args.cutoff})."
    )

    single_scores = RepeatedScores("single_task", runs["single_task"])
    multi_scores = RepeatedScores("multi_task", runs["multi_task"])
    print(f"\n{'arm':<14} {'R2':>16} {'MAE':>16} {'Spearman':>9} {'top 10%':>8}")
    for scores in (single_scores, multi_scores):
        print(
            f"{scores.split:<14} {str(scores.r2):>16} {str(scores.mae):>16}"
            f" {scores.spearman.mean:>9.3f} {scores.top_hit_rate.mean:>8.2f}"
        )

    print()
    for label, single_metric, multi_metric, higher_is_better in (
        ("R2", single_scores.r2, multi_scores.r2, True),
        ("MAE", single_scores.mae, multi_scores.mae, False),
        ("top 10%", single_scores.top_hit_rate, multi_scores.top_hit_rate, True),
    ):
        gain = multi_metric.mean - single_metric.mean
        if not higher_is_better:
            gain = -gain
        noise = max(single_metric.sd, multi_metric.sd)
        verdict = "beyond the noise" if gain > noise else "inside the noise, so undecided"
        print(f"  {label:<8} {gain:+.3f} for multi-task, spread {noise:.3f}  ->  {verdict}")
    print(
        "\nA gain smaller than the run-to-run spread is not evidence of anything."
        " See docs/STEP6_PLAN.md for why this stage is expected to be underpowered."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="satori", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("describe", help="properties of one or more SMILES strings")
    p.add_argument("smiles", nargs="*", help="SMILES strings (default: built-in examples)")
    p.set_defaults(func=cmd_describe)

    p = sub.add_parser("screen", help="filter and rank a CSV library by QED")
    p.add_argument("csv", help="CSV file with 'name' and 'smiles' columns")
    p.add_argument("--drug-like", action="store_true", help="keep only Lipinski passes")
    p.add_argument("--top", type=int, help="keep only the best N")
    p.add_argument("--out", help="write the ranked results to this CSV")
    p.set_defaults(func=cmd_screen)

    p = sub.add_parser("fetch-chembl", help="download and clean activity data for a target")
    p.add_argument("target", help="ChEMBL target ID, e.g. CHEMBL203 (EGFR)")
    p.add_argument("--type", default="IC50", help="activity type (default: IC50)")
    p.add_argument("--out-dir", default="data/chembl", help="where to save (default: data/chembl)")
    p.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_ACTIVE_THRESHOLD,
        help=f"pChEMBL cut-off for 'active' (default: {DEFAULT_ACTIVE_THRESHOLD})",
    )
    p.add_argument("--refresh", action="store_true", help="download again even if cached")
    p.set_defaults(func=cmd_fetch_chembl)

    p = sub.add_parser("similar", help="find the molecules most similar to a query")
    p.add_argument("query", help="a SMILES string, or a name present in the library")
    p.add_argument("csv", help="library CSV with 'name' and 'smiles' columns")
    p.add_argument("--top", type=int, default=10, help="how many neighbours (default: 10)")
    p.add_argument("--min", type=float, default=0.0, help="minimum similarity (default: 0)")
    p.set_defaults(func=cmd_similar)

    p = sub.add_parser("cluster", help="group a library into series of similar molecules")
    p.add_argument("csv", help="library CSV with 'name' and 'smiles' columns")
    p.add_argument(
        "--cutoff",
        type=float,
        default=DEFAULT_CUTOFF,
        help=f"similarity needed to join a cluster (default: {DEFAULT_CUTOFF})",
    )
    p.add_argument("--top", type=int, default=10, help="how many clusters to show (default: 10)")
    p.set_defaults(func=cmd_cluster)

    p = sub.add_parser("train", help="predict potency from structure, scored two ways")
    p.add_argument("csv", help="library CSV with 'smiles' and a value column")
    p.add_argument("--column", default="pchembl", help="what to predict (default: pchembl)")
    p.add_argument(
        "--test-fraction",
        type=float,
        default=DEFAULT_TEST_FRACTION,
        help=f"share of molecules held out (default: {DEFAULT_TEST_FRACTION})",
    )
    p.add_argument("--cutoff", type=float, default=DEFAULT_CUTOFF, help="clustering cut-off")
    p.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEATS,
        help=f"how many times to repeat each split (default: {DEFAULT_REPEATS})",
    )
    p.add_argument("--trees", type=int, default=DEFAULT_TREES, help="trees in the forest")
    p.add_argument(
        "--model",
        default="random_forest",
        choices=sorted(bench.MODELS),
        help="which model to fit (default: random_forest; see `benchmark` for a comparison)",
    )
    p.add_argument("--seed", type=int, default=0, help="random seed, for repeatable splits")
    p.add_argument("--save", help="save the cluster-split model to this file")
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("benchmark", help="compare models and representations fairly")
    p.add_argument("csv", help="library CSV with 'smiles' and a value column")
    p.add_argument("--column", default="pchembl", help="what to predict (default: pchembl)")
    p.add_argument("--cutoff", type=float, default=DEFAULT_CUTOFF, help="clustering cut-off")
    p.add_argument(
        "--test-fraction", type=float, default=DEFAULT_TEST_FRACTION, help="share held out"
    )
    p.add_argument("--repeats", type=int, default=3, help="repeats per contestant (default: 3)")
    p.add_argument("--seed", type=int, default=0, help="random seed")
    p.add_argument(
        "--only",
        nargs="+",
        metavar="MODEL",
        help=f"limit to these models: {', '.join(bench.MODELS)}",
    )
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser("multitask", help="does data from related proteins help?")
    p.add_argument("csv", help="the library holding the protein we are judged on")
    p.add_argument("--also", nargs="+", help="further libraries to learn from")
    p.add_argument("--primary", default="wild_type", help="task to judge on (default: wild_type)")
    p.add_argument("--column", default="pchembl", help="what to predict (default: pchembl)")
    p.add_argument("--features", default="ecfp4", help="representation (default: ecfp4)")
    p.add_argument(
        "--model", default="gradient_boosting", choices=sorted(bench.MODELS), help="which model"
    )
    p.add_argument("--cutoff", type=float, default=DEFAULT_CUTOFF, help="similarity cut-off")
    p.add_argument(
        "--test-fraction", type=float, default=DEFAULT_TEST_FRACTION, help="share held out"
    )
    p.add_argument("--repeats", type=int, default=5, help="repeats (default: 5)")
    p.add_argument("--seed", type=int, default=0, help="random seed")
    p.set_defaults(func=cmd_multitask)

    p = sub.add_parser("labels", help="measure how much of the error is the data's")
    p.add_argument("csv", help="library CSV from fetch-chembl (needs n_measurements, spread)")
    p.add_argument("--column", default="pchembl", help="what to predict (default: pchembl)")
    p.add_argument("--features", default="ecfp4", help="representation (default: ecfp4)")
    p.add_argument(
        "--model", default="gradient_boosting", choices=sorted(bench.MODELS), help="which model"
    )
    p.add_argument(
        "--min-measurements",
        type=int,
        default=DEFAULT_MIN_MEASUREMENTS,
        help=f"measurements needed to trust a label (default: {DEFAULT_MIN_MEASUREMENTS})",
    )
    p.add_argument(
        "--max-spread",
        type=float,
        default=DEFAULT_MAX_SPREAD,
        help=f"widest disagreement still trusted (default: {DEFAULT_MAX_SPREAD})",
    )
    p.add_argument(
        "--schemes",
        nargs="+",
        default=["count", "agreement", "both"],
        choices=list(WEIGHT_SCHEMES),
        help="weighting schemes to try",
    )
    p.add_argument("--cutoff", type=float, default=DEFAULT_CUTOFF, help="clustering cut-off")
    p.add_argument(
        "--test-fraction", type=float, default=0.3, help="share held out (default: 0.3)"
    )
    p.add_argument("--repeats", type=int, default=5, help="repeats per row (default: 5)")
    p.add_argument("--seed", type=int, default=0, help="random seed")
    p.set_defaults(func=cmd_labels)

    p = sub.add_parser("predict", help="predict with a saved model")
    p.add_argument("model", help="a model file written by `train --save`")
    p.add_argument("smiles", nargs="+", help="one or more SMILES strings")
    p.set_defaults(func=cmd_predict)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
