.PHONY: cv-check

cv-check:
	python3 tools/compare_cv_to_website.py --cv ../master_cv.docx --site . --output CV_WEBSITE_DIFF.md
	@echo ""
	@echo "Review CV_WEBSITE_DIFF.md, then follow UPDATE_WEBSITE.md."
