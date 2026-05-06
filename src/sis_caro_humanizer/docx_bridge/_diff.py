"""_diff.py — diff_text_sections: paragraph-by-paragraph diff of two texts."""
from __future__ import annotations


def diff_text_sections(original: str, revised: str) -> list[dict]:
    """Compare two texts paragraph-by-paragraph and return a diff report.

    Parameters
    ----------
    original:
        The original text (before lecturer changes).
    revised:
        The revised / accepted text (after ``accept_tracked_changes``).

    Returns
    -------
    list of dicts with keys:
      ``original`` (str) — original paragraph text (empty string if inserted)
      ``revised``  (str) — revised paragraph text (empty string if deleted)
      ``changed``  (bool)
      ``paragraph_idx`` (int) — 0-based index in the *revised* list
    """
    import difflib

    def _split(text: str) -> list[str]:
        return [p.strip() for p in text.split("\n\n") if p.strip()]

    orig_paras = _split(original)
    rev_paras = _split(revised)

    matcher = difflib.SequenceMatcher(None, orig_paras, rev_paras, autojunk=False)
    sections: list[dict] = []

    rev_idx = 0  # tracks position in the revised list

    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode == "equal":
            for k, para in enumerate(rev_paras[j1:j2]):
                sections.append(
                    {
                        "original": para,
                        "revised": para,
                        "changed": False,
                        "paragraph_idx": j1 + k,
                    }
                )
        elif opcode == "replace":
            # Pair up as many orig ↔ revised as possible; extras are inserts/deletes.
            orig_chunk = orig_paras[i1:i2]
            rev_chunk = rev_paras[j1:j2]
            max_len = max(len(orig_chunk), len(rev_chunk))
            for k in range(max_len):
                orig_text = orig_chunk[k] if k < len(orig_chunk) else ""
                rev_text = rev_chunk[k] if k < len(rev_chunk) else ""
                # paragraph_idx in the revised list — use j1+k for revised side
                p_idx = j1 + k if k < len(rev_chunk) else j2 - 1
                sections.append(
                    {
                        "original": orig_text,
                        "revised": rev_text,
                        "changed": True,
                        "paragraph_idx": p_idx,
                    }
                )
        elif opcode == "delete":
            for k, para in enumerate(orig_paras[i1:i2]):
                sections.append(
                    {
                        "original": para,
                        "revised": "",
                        "changed": True,
                        "paragraph_idx": j1,  # insertion point in revised
                    }
                )
        elif opcode == "insert":
            for k, para in enumerate(rev_paras[j1:j2]):
                sections.append(
                    {
                        "original": "",
                        "revised": para,
                        "changed": True,
                        "paragraph_idx": j1 + k,
                    }
                )

    return sections
