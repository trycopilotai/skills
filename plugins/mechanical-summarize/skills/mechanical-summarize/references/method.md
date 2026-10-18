# Method basis

This skill combines three existing ideas without installing
their model stacks.

## Deletion-based compression

[Sentence Compression by Deletion with LSTMs](https://aclanthology.org/D15-1042/)
treats shortening as deletion from a source sentence. This
skill adopts the deletion boundary but uses an agent-guided
editorial pass instead of the paper's trained model.

The practical invariant is an ordered lexical subsequence:
every retained lexical token must occur in the source in the
same order.

## KEEP and DELETE operations

[LaserTagger](https://github.com/google-research/lasertagger)
defines token-level KEEP, DELETE, ADD, and sentence-SWAP
operations. This skill permits only KEEP and DELETE. That
restriction makes lexical additions and reorderings
mechanically detectable.

LaserTagger's repository describes vocabulary optimization,
data conversion, model fine-tuning, and prediction. Those
dependencies are unnecessary for this human-readable,
single-document workflow.

## Word-budget allocation

[With Measured Words](https://aclanthology.org/2021.eacl-main.139/)
applies a requested compression ratio to both individual
sentences and sentence sequences, and describes bounded
knapsack allocation across a sequence.

This skill reuses the length-budget idea: measure raw word
savings across candidate deletion spans and seek the closest
safe result at or above the target floor. It does not reuse
the paper's learned sentence-compressibility predictor.

## Boundary

This is compression, not abstractive summarization. The
output does not synthesize, paraphrase, reorder, or infer.
Semantic review remains required because word counts and
subsequence checks cannot prove that a deletion preserved
meaning or voice.
