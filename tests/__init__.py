"""Testpakke.

Filen er tom med vilje. Den findes udelukkende for at pytest (importmode
"prepend") indsætter *repoets rod* i sys.path frem for tests/ — ellers kan
testene ikke `import src.data_loader`. src/ er selv en pakke (src/__init__.py),
så roden er det korrekte sys.path-element.
"""
