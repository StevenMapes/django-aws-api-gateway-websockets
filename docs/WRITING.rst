#############
Writing Rules
#############

These rules apply to all written communication except code itself: documentation, commit messages, PR descriptions, change logs, and SOPs.

Documentation Format
====================

- Project documentation in ``docs/`` is written in reStructuredText (``.rst``) and built with Sphinx into Read the Docs style HTML. Add every new page to a ``toctree``, usually in ``docs/index.rst``, or Sphinx warns that it is not included.
- Two folders stay in Markdown (``.md``), because people read them as plain files rather than as built pages:

  - ``docs/tasks/``: plans, task lists and the roadmap.
  - ``docs/sessions/``: session handoff notes (the file name format is set in ``CLAUDE.md``).

  Sphinx only reads ``.rst`` files, so these folders are never part of the built documentation.
- ``README.md`` files outside ``docs/`` (for example ``docker/README.md`` and ``infrastructure/README.md``) stay in Markdown, because GitHub shows them next to the code. Keep them short and link to the full ``.rst`` page in ``docs/``.
- When converting a Markdown page, keep its content, then fix it to the rules below: the heading hierarchy, admonitions instead of block quotes, and ``.. code-block::`` directives.
- Never put documentation under ``static/``. Everything there is published to S3 and CloudFront.
- ``docs/dependencies.rst`` is generated. After changing any requirement file, run ``.venv/bin/python docs/tools/generate_dependencies.py`` instead of editing the page.

Public-Facing Documentation
===========================

Documentation written for attendees or the public, such as ``docs/guides/attendees.rst`` and its PDF, never mentions refunds: how to get one, when they are given, or the refund choices after a cancelled event. Point people to the contact form (``/contact/``) for help instead (Steve, 28 September 2026). Staff guides, process documents and the developer documentation may describe refunds in full.

Core Clarity Rules (after Orwell)
=================================

- Never use a metaphor, simile, or figure of speech you are used to seeing in print.
- Never use a long word where a short one will do.
- If it is possible to cut a word out, cut it out.
- Prefer the active voice; use the passive only where the active would be awkward or misleading.
- Never use a foreign phrase or vague filler word if a plain English equivalent exists.
- Break any of these rules sooner than say anything outright barbarous.

Technical Vocabulary
====================

- Django, Python, and library-specific terms are precise vocabulary, not jargon to avoid. Use the correct term even when a simpler word exists: queryset, middleware, signal, migration, serializer, context processor, and so on.
- Always use backticks for: function and method names, class names, module names, settings keys, file paths, URLs, and shell commands — both in prose and in headings.
- When referencing a Django or Python built-in, link to the official documentation on first mention in each page.

Language and Style
==================

- Write in British English throughout: use -ise not -ize, colour not color, behaviour not behavior, and so on. Do not mix British and American spellings within the same document or project.
- Use present tense for describing behaviour: "Returns a queryset", not "Will return".
- Avoid vague intensifiers: remove "very", "quite", "fairly", "simply", and "basically" wherever they appear.

RST and Read the Docs Conventions
=================================

- Follow the Sphinx heading hierarchy consistently across all files: ``#`` with overline for the page title, ``=`` for sections, ``-`` for subsections, ``~`` for sub-subsections. Do not skip levels.
- Use admonitions correctly and sparingly:

  - ``.. note::`` for information the reader would benefit from but could skip.
  - ``.. warning::`` for actions that may cause data loss, breakage, or security risk.
  - ``.. important::`` for information the reader must not miss.
  - ``.. deprecated::`` for features being removed; always state the version and the replacement.

- Mark version changes with the appropriate directive: ``.. versionadded:: x.y``, ``.. versionchanged:: x.y``, ``.. deprecated:: x.y``.
- Use Sphinx cross-reference roles rather than plain hyperlinks for internal references: ``:ref:``, ``:doc:``, ``:class:``, ``:func:``, ``:meth:``, ``:attr:``, ``:setting:``, ``:data:``.
- Write docstrings in Sphinx format using ``:param name:``, ``:type name:``, ``:returns:``, ``:rtype:``, and ``:raises ExceptionType:``. Be consistent across the entire project.

RST Code Blocks and blacken-docs
================================

The ``blacken-docs`` pre-commit hook runs ``black`` on every ``.. code-block:: python`` block in RST files. Use ``.. code-block:: text`` instead of ``.. code-block:: python`` for any block that is not fully valid, parseable Python, including:

- Illustrative snippets containing ``...`` as a placeholder in a dict, function parameter list, or function body
- Pseudo-code or abbreviated examples showing structure rather than runnable code
- Settings extracts that mix Python syntax with placeholder values (e.g., ``config(...)`` calls inside a dict shown as an example)

Only use ``.. code-block:: python`` for complete, syntactically valid Python that ``black`` can format without errors. When in doubt, use ``.. code-block:: text``.

Commit Messages and PR Descriptions
===================================

- Use the imperative mood for the subject line: "Add pagination to invoice list", not "Added" or "Adds".
- Keep the subject line to 72 characters or fewer.
- Separate the subject from the body with a blank line.
- The body should explain what changed and why, not how (the code shows how).
- Reference issue or ticket numbers in the body, not the subject line.

Change Logs
===========

- Group entries under: ``Added``, ``Changed``, ``Fixed``, ``Deprecated``, ``Removed``, ``Security``.
- Every entry is a single sentence in the past tense, describing the user-visible effect: "Fixed", "Added", "Removed".
- Avoid internal implementation detail unless it directly affects how the user calls the code.

What Good Looks Like
====================

- A reader unfamiliar with the codebase should understand what a page is about from its first two sentences.
- A reader familiar with Django should be able to scan headings and backtick-formatted names to find what they need without reading every word.
- No sentence should require a second reading to understand.
