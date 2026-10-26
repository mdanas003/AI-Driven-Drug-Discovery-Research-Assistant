"""Step 4: fingerprints, similarity search and clustering.

The oldest useful idea in medicinal chemistry: **similar molecules tend to
have similar activity**. To use it we need a way to measure "similar".

A **fingerprint** turns a molecule into a long row of yes/no bits. We use
Morgan fingerprints (also called ECFP4): walk over every atom, look at the
neighbourhood around it out to two bonds away, and switch on a bit for each
distinct neighbourhood found. Two molecules sharing many bits share many
chemical fragments.

**Tanimoto similarity** then compares two fingerprints:

    shared bits / (bits in either one)

1.0 means identical fingerprints, 0.0 means nothing in common. As a rough
guide, above 0.7 is clearly related, 0.4 to 0.7 is a family resemblance,
and below 0.3 is unrelated.
"""

from dataclasses import dataclass

from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator

from satori.molecule import parse_smiles, strip_salts

# radius=2 means "look two bonds out from each atom", which is what makes
# this ECFP4. 2048 bits is the usual size: long enough that unrelated
# fragments rarely collide onto the same bit.
RADIUS = 2
N_BITS = 2048
_generator = rdFingerprintGenerator.GetMorganGenerator(radius=RADIUS, fpSize=N_BITS)

# Default cut-off for calling two molecules "the same series".
DEFAULT_CUTOFF = 0.6


def fingerprint(mol: Chem.Mol):
    """The molecule as 2048 on/off bits."""
    return _generator.GetFingerprint(mol)


def fingerprint_of(smiles: str):
    """Fingerprint a SMILES string, salts removed first."""
    return fingerprint(strip_salts(parse_smiles(smiles)))


def fingerprint_library(rows: list[dict]) -> tuple[list[dict], list, list[str]]:
    """Fingerprint every row that has a readable structure.

    Returns the usable rows, their fingerprints (same order), and the names
    of the rows that had to be skipped.
    """
    kept, fps, skipped = [], [], []
    for row in rows:
        try:
            fps.append(fingerprint_of(row["smiles"]))
        except ValueError:
            skipped.append(row["name"])
            continue
        kept.append(row)
    return kept, fps, skipped


def similarity(a, b) -> float:
    """Tanimoto similarity between two fingerprints, from 0.0 to 1.0."""
    return DataStructs.TanimotoSimilarity(a, b)


def similarities(query, library: list) -> list[float]:
    """Compare one fingerprint against many, in one fast C++ call."""
    return DataStructs.BulkTanimotoSimilarity(query, library) if library else []


@dataclass
class Neighbour:
    index: int
    similarity: float


def most_similar(query, library: list, top: int = 10, minimum: float = 0.0) -> list[Neighbour]:
    """The most similar library entries to a query fingerprint, best first."""
    scored = [
        Neighbour(i, round(score, 3))
        for i, score in enumerate(similarities(query, library))
        if score >= minimum
    ]
    scored.sort(key=lambda n: n.similarity, reverse=True)
    return scored[:top]


@dataclass
class Cluster:
    centre: int  # index of the molecule the cluster formed around
    members: list[int]  # every member, including the centre

    def __len__(self) -> int:
        return len(self.members)


def cluster(library: list, cutoff: float = DEFAULT_CUTOFF, order: list[int] | None = None) -> list[Cluster]:
    """Group molecules into series of near-neighbours (sphere exclusion).

    Walk the molecules in `order`. Each unassigned molecule becomes the
    centre of a new cluster and claims every unassigned molecule within
    `cutoff` similarity of it. The order therefore decides which molecules
    get to be centres, so passing the most potent ones first makes each
    cluster centre a compound worth looking at.

    This needs memory for only one row of comparisons at a time, which
    matters: a full distance matrix for 8,000 molecules is 32 million
    numbers.
    """
    unassigned = set(range(len(library)))
    clusters: list[Cluster] = []
    for i in order if order is not None else range(len(library)):
        if i not in unassigned:
            continue
        unassigned.discard(i)
        scores = similarities(library[i], library)
        members = [i] + [j for j in sorted(unassigned) if scores[j] >= cutoff]
        unassigned.difference_update(members)
        clusters.append(Cluster(i, members))
    clusters.sort(key=len, reverse=True)
    return clusters
