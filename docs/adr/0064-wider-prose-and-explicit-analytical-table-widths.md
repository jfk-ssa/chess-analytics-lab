# 0064. Wider prose and explicit analytical table widths

- Status: accepted
- Date: 2026-10-09

The owner approved refining the preceding reading-width change: use `78ch`
prose and contents, keep headings free to extend, and let comparison tables and
dense analytical tables use the full page canvas. Remove the article-wide
maximum; constrain individual reading blocks instead. Ordinary tables and
research cards retain the reading measure. The builder explicitly marks
comparison-guide tables, four-plus-column tables, and proposed-relation tables
as wide. Contain table overflow rather than expanding the page. Remove the
nested Markdown contents wrapper and reduce the remaining panel's padding.
Use one shared CSS reading-width token and preserve the common left edge.
