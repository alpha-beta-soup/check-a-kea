# Translations

Generate a translation source file for a new locale:

```bash
pylupdate5 ../*.py ../core/*.py -ts check_a_kea_<locale>.ts
```

Translate the strings inside the `.ts` file (it is plain XML), then compile it:

```bash
lrelease check_a_kea_<locale>.ts
```

The resulting `.qm` binary is loaded automatically at plugin startup when QGIS is
set to the matching locale (`Settings → Options → General → User interface translation`).
