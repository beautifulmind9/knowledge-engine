# Source identity resolution

The filename-derived title in Add is provisional. The first explicit edit in
the confirmation surface marks the title as user-confirmed; an entered author
is also user-confirmed. Those choices are stored on the existing source record
as title/author origins. Older sources without origin fields are treated as
user-owned, so a later read never silently renames them. The source-detail
identity editor also saves both values as user-confirmed. Saving an empty
optional author confirms that no author should be shown and prevents a later
read from filling it automatically.

During the deterministic read already performed by Add, KE checks structured
EPUB, PDF and DOCX title/creator metadata, then checks extracted opening text
for an explicit title heading/label and an explicitly marked byline. It makes
no extra provider request. Explicit material title/byline evidence takes
precedence over embedded metadata when they conflict, because embedded fields
can be stale after a document is repurposed. Embedded metadata is used when
clearer visible evidence is absent. A person's name in ordinary prose is never
promoted to author. One standalone name directly below a plain opening title
may be shown as a reviewable suggestion; multiple adjacent names remain
ambiguous and unset.

If stronger title evidence is found, it replaces only a filename-origin title.
If an explicit byline or embedded creator is found, it fills only an
unconfirmed author. Metadata parser errors do not fail deterministic reading.
If reading fails first, the filename suggestion remains available and its
source-detail label identifies it as temporary. A metadata/title conflict is
retained as a small review cue. This is a narrow deterministic mechanism for
books and common document files, not a general identity classifier.
