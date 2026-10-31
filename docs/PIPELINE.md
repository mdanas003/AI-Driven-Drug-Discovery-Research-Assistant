# Where we are, and why the route looks strange

You described the textbook pipeline, and you described it correctly:

```
data  ->  clean  ->  feature engineering  ->  pick a model
                                                    |
                                       split train / test
                                                    |
                                        train on train
                                                    |
                                         test on test
                                                    |
                                              stats
```

That is the whole of it, and Satori has **already done it** — all of it, end to end, at
Step 5. We got stats. The stats were good: R² 0.59, MAE 0.64 log units, 49% of the top
10% found.

So why are we on Step 6 instead of shipping?

Because in drug discovery that pipeline has a hole in it, and the hole is in the one box
everybody trusts: **split**.

---

## 1. Why the textbook split lies here

In most ML, a random split is fine. If you are predicting house prices, the test houses
are drawn from the same world as the training houses, and that is also the world the model
will meet in production.

Chemistry is not like that. Pharmaceutical data is **clustered by history**. A company
finds one molecule that works, then makes 400 near-copies of it (change a methyl, move a
fluorine) and tests all 400. Our EGFR table is not 8,450 independent molecules. It is
maybe 300 ideas with 8,450 variations on them.

Now split that randomly. Variation #212 of an idea goes into test; variations #1–211 go
into training. The model is asked a question whose answer is sitting in its training set
with one atom moved.

- **CS view:** the independence assumption behind train/test is violated. The test set is
  not a sample of the deployment distribution, it is a sample of the training
  distribution. The score measures interpolation, and we would report it as
  generalisation.
- **Biology view:** a chemist does not need a model to tell them that the fluorine analogue
  of a known inhibitor is also an inhibitor. They need it to say whether a molecule from a
  family nobody has tried will work. That is the only question worth money, and it is the
  one a random split never asks.

So the pipeline does not end at "stats". In this field it ends at *"stats, and a protocol
that says what the stats mean"* — and then you go back and attack your own protocol until
it stops being wrong.

That loop is where Satori has been for the last five stages. Here is the whole route.

---

## 2. The flow, from the beginning to the end

```
                         ===== PART I: THE TEXTBOOK PIPELINE =====

  [Step 1]  a molecule as text                           src/satori/molecule.py
  SMILES string --> RDKit graph --> 7 properties --> Lipinski verdict
       "CC(=O)Oc1ccccc1C(=O)O"  -->  MW 180, logP 1.3, QED 0.55  -->  PASS
                         |
                         v
  [Step 2]  a library instead of one molecule             src/satori/library.py
  CSV --> parse each --> drop invalid --> dedupe by canonical SMILES --> rank by QED
                         |
                         v
  [Step 3]  REAL DATA  (the "data" box of your chart)     src/satori/chembl.py
  ChEMBL web API, target CHEMBL203 (EGFR), assay_type=B, IC50
       26,600 raw measurements
                         |
       CLEAN:  strip salts/hydrates (largest fragment)
               drop unparseable, drop missing pChEMBL
               LABEL each row wild-type vs T790M / L858R / ...
               AGGREGATE duplicates: median per (structure, protein)
                         |
       10,381 molecules  =  8,450 wild-type  +  4,060 mutant rows
       + provenance JSON (which release, which filters, when)
                         |
                         v
  [Step 4]  FEATURE ENGINEERING                           src/satori/similarity.py
  molecule graph --> Morgan/ECFP4 fingerprint --> 2,048-bit vector     features.py
       "does fragment #1,731 appear in this molecule?" x 2048
  + Tanimoto similarity, + sphere-exclusion clustering (-> ~chemical families)
                         |
                         v
  [Step 5]  MODEL + SPLIT + TRAIN + TEST + STATS          src/satori/model.py
       random split      -> R2 0.73   <-- flattering, and we said so
       cluster split     -> R2 0.59   <-- hold out whole families
       repeats x5 seeds  -> +/- spread on every number  = a DETECTION FLOOR
                         |
                         v
                  stats exist.  Pipeline complete.
                  ...so now the real work starts.


                    ===== PART II: ATTACKING OUR OWN ANSWER =====
                (each stage kills one explanation for why 0.59 isn't 0.9)

  [5b] "use a better model?"                              benchmark.py
       8 contestants: random forest, LightGBM, Tanimoto-SVR, Ridge
                     x  ECFP4 / ECFP4-counts / ECFP6 / +descriptors
       --> SIX-WAY TIE inside the spread.
       VERDICT: model class is not the bottleneck. Stop shopping for models.
       Also measured the CEILING: repeat experiments disagree by 0.775 log
       units, and our MAE is 0.638 -- we are already inside the noise of the
       data itself on familiar chemistry.
                         |
                         v
  [5c] "use cleaner labels?"                              labels.py
       weight by measurement count / by agreement / filter to confident only
       --> weighting: null result. 8,450 noisy labels BEAT 761 clean ones.
       VERDICT: label quality is not the bottleneck either. Quantity wins.
                         |
                         v
  [6.0] "show it more proteins?"  (plumbing only)         multitask.py
       pool EGFR wild-type + its mutants, one-hot "which protein" column
       BUT FIRST: close the leak. 42% of mutant rows are molecules that also
       appear in the wild-type set -- the same molecule, different protein.
       --> honest_training_set() + audit() that must pass on every split
       --> RESULT: no effect, exactly as pre-registered (too small to detect)
                         |
       AND, as a side effect, the thing that mattered most:
                         v
       ***  OUR STEP 5 SPLIT WAS LEAKING  ***
       Sphere exclusion only bounds distance to cluster CENTRES. Two molecules
       in different clusters can still be near-twins of each other. 2,844 rows
       were sitting in training within 0.6 Tanimoto of a test molecule.
                         |
       STRICT PROTOCOL: drop anything within 0.6 of any test molecule
       --> re-ran all 8 contestants:  R2 0.59  ->  0.43
       --> and the ranking CHANGED: ECFP6 fell out of the tie, Ridge collapsed
           to -0.89 (worse than guessing the mean).
       VERDICT: the loose protocol had been picking the winner on memorisation.
                         |
                         v
            HONEST HEADLINE, the number we actually stand behind:
            on chemistry it has never seen, Satori finds 30% of the true
            top 10% -- three times better than chance.


                         ===== PART III: NOT DONE YET =====

  [6.1] the only hypothesis left standing: NOT ENOUGH CHEMISTRY.
        One protein's 8,450 molecules is a thin sample of chemical space.
        --> download ChEMBL's bulk SQLite release (5.76 GB, ~35 GB unpacked)
        --> SQL for per-target IC50 counts across ~450 human kinases
        --> extract a shortlist to CSVs in the Step 3 format
        --> Setting B: tyrosine kinases (close relatives)
            Setting C: the whole kinome (volume)
        Pre-registered in docs/STEP6_PLAN.md with a success criterion AND a
        kill criterion, so "no effect" is a publishable answer, not a failure.
        STATUS: planned, needs your go-ahead on the disk space.

  [7]   Targets: given a disease, which protein should we even aim at?
        (Open Targets) -- turns Satori from "score this molecule" into
        "here is what to work on".

  [8]   Product: web UI, API, docking / 3D structure, generative models
        (propose new molecules, not just score given ones), GPU, deployment.
        Each added only once the step before it works.
```

---

## 3. So, concretely: what data do we have?

Everything so far rests on **one protein**:

| File | Rows | What it is |
|---|---:|---|
| `CHEMBL203_IC50_raw.csv` | 26,600 | every IC50 measurement ChEMBL has for EGFR, untouched |
| `CHEMBL203_IC50.csv` | 10,381 | cleaned and aggregated, all variants |
| `CHEMBL203_IC50_wild_type.csv` | **8,450** | normal EGFR — this is what we train and score on |
| `CHEMBL203_IC50_mutant.csv` | 4,060 | T790M, L858R etc. — different proteins, kept apart on purpose |

`CHEMBL203` is EGFR, a protein that sits in the cell membrane and tells the cell to divide.
When it is mutated or overproduced the "divide" signal never stops — that is non-small-cell
lung cancer. Blocking it is how gefitinib, erlotinib and osimertinib work. One label, one
number per molecule: **pChEMBL** = −log₁₀(concentration needed to halve the protein's
activity). 7.0 means nanomolar and interesting; 5.0 means micromolar and probably useless.
+1 = ten times more potent.

That is the whole dataset. 8,450 rows against ~10⁶⁰ possible drug-like molecules. Stage 6.1
exists because that ratio, not our choice of model, is the thing that is actually limiting us.

---

## 4. The one-sentence answer

We are not stuck before the stats. We finished the textbook pipeline at Step 5 and have
spent every stage since **dismantling our own good number** — eliminating the model, the
labels, and finally our own split — until only one explanation was left. Stage 6.1 is the
first stage in a while that tries to *improve* something rather than disprove it.
