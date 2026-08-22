# kjincs.github.io

## Updating the website after changing the CV

After replacing `../master_cv.docx`, run:

```bash
make cv-check
```

This creates `CV_WEBSITE_DIFF.md` with numbered review candidates. It does not
edit the website. Follow [UPDATE_WEBSITE.md](UPDATE_WEBSITE.md) to review,
preview, commit, and publish approved changes.
