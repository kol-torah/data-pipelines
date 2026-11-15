"""Scripts that were run once, against one specific state of the data, and never again.

Kept rather than deleted because they are the record of *how* something irreversible was
done — which key an object moved from, what was verified before anything was dropped —
and that record is worth more than the disk space once the thing has been done.

Nothing here is part of a pipeline, imported by one, or scheduled. Anything under this
package should be treated as frozen: **self-contained by preference**, so a later
refactor of the code it once called cannot silently change what the archive appears to
say. If one of these ever needs to run again, that is a sign it was not one-off, and it
belongs back in a pipeline.

The same idea as `documents/plans/implemented/`, for code.
"""
