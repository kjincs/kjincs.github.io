# Update the Website from `master_cv.docx`

Use this review-first workflow whenever `master_cv.docx` changes. The comparison
tool only creates a report; it never edits, commits, or pushes the website.

## Quick start

1. Replace `/Users/dongjin/codex_projects/UArk_homepage/master_cv.docx` with the
   latest CV.
2. Open Terminal and run:

   ```bash
   cd /Users/dongjin/codex_projects/UArk_homepage/website
   make cv-check
   ```

3. Open `CV_WEBSITE_DIFF.md` and review the numbered candidates:
   - `C##`: CV content that may be missing or different on the website.
   - `W##`: website content that may be absent or different in the CV.
4. Tell Codex which IDs to apply. For example:

   > Apply C01, C03, and W02. Do not change the external CV PDF link. Show me a
   > local preview and do not commit or push yet.

5. Review the local preview. Request corrections if needed.
6. When everything looks right, tell Codex:

   > Commit and push the approved website changes.

7. Allow a few minutes for GitHub Pages to publish the new version.

## Important review rules

- Treat the report as a checklist, not an instruction to synchronize everything.
- The homepage should remain selective and concise; the CV is comprehensive.
- The selected-publications page and full-publications page serve different
  purposes.
- Alumni wording, student status, awards, dates, and publication status deserve
  manual review.
- The Dropbox CV PDF link is maintained separately unless explicitly approved.
- Never paste a GitHub token into chat. Git should reuse the token saved in the
  macOS Keychain when pushing.

## Direct script usage

The convenient command is `make cv-check`. The equivalent direct command is:

```bash
python3 tools/compare_cv_to_website.py \
  --cv ../master_cv.docx \
  --site . \
  --output CV_WEBSITE_DIFF.md
```

Use `python3 tools/compare_cv_to_website.py --help` for tuning options. The
comparison is approximate and intentionally favors showing questionable items
for human review rather than silently changing the site.

## Reminder

The repository README always displays the `make cv-check` reminder. A useful
personal habit is: **replace the CV, then immediately run `make cv-check`**.
