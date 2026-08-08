#!/bin/bash
# Installation de CE greffon dans le venv Spyder d'une machine SmartOS (mecanisme .pth
# "editable" : le greffon reste dans ce depot, seul un pointeur part dans site-packages).
# Sorti d'installation_SmartPythonEditor.sh le 08/08/2026 (demande utilisateur : les notes et
# verifications de chaque greffon vivent dans SON depot) - le script SmartOS n'est plus qu'un
# appel d'une ligne vers ce fichier. L'installation DISTRIBUEE (install.sh du fork
# SmartPythonEditor) n'utilise PAS ce script : elle passe par pip.
#
# Usage : installer_dans_venv.sh <python du venv Spyder> <sans_tests true|false> \
#                                <install_spyder_plugin.py> <spyder_config_set.py> <spyder.ini>
set -u
SPYDER_PYTHON="${1:?python du venv Spyder}"
SANS_TESTS="${2:-true}"
OUTIL_INSTALL="${3:?chemin de install_spyder_plugin.py}"
OUTIL_CONFIG="${4:?chemin de spyder_config_set.py}"
SPYDER_INI="${5:?chemin du spyder.ini}"
PLUGIN_DIR="$(cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/.." && pwd)"

# =============================================================================
# Plugin Spyder "Terminal natif" — le moteur de Konsole dans un dock
# =============================================================================
# Installe le greffon versionne dans ce depot (spyder_native_terminal/,
# qui REMPLACE le greffon amont spyder-terminal (desinstalle le 26/07/2026).
#
# POURQUOI CE REMPLACEMENT. spyder-terminal affichait xterm.js dans un QWebEngineView
# alimente par un serveur tornado + terminado : trois briques lourdes pour un terminal,
# quatre patchs SmartOS a maintenir pour qu'il survive a Qt6, et un serveur qui
# SURVIVAIT a la fermeture de Spyder (constate le 26/07/2026 : plusieurs processus
# "spyder_terminal.server --port 807x" encore vivants). Le greffon maison n'a ni serveur,
# ni port, ni navigateur : le pty est ouvert dans le processus de Spyder et le rendu est
# celui de Konsole.
#
# UN SEUL MOTEUR : QTermWidget, via un binding shiboken construit ICI contre le PySide6
# du venv. Un emulateur VT en Python pur avait servi de repli le temps d'une matinee ; il
# a ete supprime le 26/07/2026 sur demande de l'utilisateur — sept cents lignes a
# maintenir pour une plateforme jamais testee.
#
# Sans binding, le greffon s'installe quand meme et AFFICHE dans son panneau ce qu'il
# faut faire pour l'obtenir. C'est volontaire : un greffon qui refuse de s'installer
# disparait de la liste des greffons, et personne ne sait pourquoi.
#
# Invocation : installation_SmartPythonEditor.sh --greffon terminal
# =============================================================================

# PAS de "set -e" : error_handler.sh installe un trap ERR interactif, incompatible
# avec errexit (cf. l'explication detaillee en tete de installation_SmartPythonEditor.sh).

if [ ! -f "$PLUGIN_DIR/pyproject.toml" ]; then
  echo "ERREUR : plugin introuvable dans $PLUGIN_DIR - abandon." >&2
  exit 1
fi

if [ ! -x "$SPYDER_PYTHON" ]; then
  echo "ERREUR : $SPYDER_PYTHON introuvable." >&2
  echo "         Installez d'abord Spyder (./installation_SmartPythonEditor.sh)." >&2
  exit 1
fi
echo "Environnement Spyder cible : $SPYDER_PYTHON"

# --- Le moteur de Konsole : prerequis puis binding ---------------------------
# Trois prerequis, tous verifiables :
#   qtermwidget       : la bibliotheque C++ (le moteur de Konsole en widget Qt).
#   libxml2-legacy    : le generateur shiboken6 est lie a libxml2 en 2.x (soname .so.2),
#                       alors qu'Arch est passe a .so.16. Sans ce paquet de
#                       compatibilite, le binaire ne DEMARRE pas, et son message
#                       ("libxml2.so.2: cannot open shared object file") ne dit pas quel
#                       paquet installer (diagnostic du 26/07/2026).
#   shiboken6_generator : le generateur lui-meme, a la version EXACTE de PySide6.
echo
echo "--- Moteur Konsole : prerequis ---"
sudo pacman -S --needed --noconfirm qtermwidget libxml2-legacy || {
  echo "ATTENTION : installation de qtermwidget/libxml2-legacy impossible." >&2
  echo "            Le greffon s'installera, mais son panneau dira que le moteur manque." >&2
}

# La version du generateur doit coller a celle de PySide6 : un generateur d'une autre
# version produit des sources qui ne compilent pas contre le shiboken installe.
VERSION_PYSIDE=$("$SPYDER_PYTHON" -c "import PySide6; print(PySide6.__version__)" 2>/dev/null)
if [ -n "$VERSION_PYSIDE" ]; then
  echo "PySide6 detecte : $VERSION_PYSIDE"
  # On appelle le pip DU VENV directement, et non `pip` sous PYENV_VERSION : ce script
  # doit rester lancable seul, sans les variables que installation_SmartPythonEditor.sh definit
  # pour lui-meme (SPYDER_VERSION, PIP_CACHE_ARGS) — avec `set -u`, s'y fier le ferait
  # mourir sur une variable non definie.
  "$SPYDER_PYTHON" -m pip install ${PIP_CACHE_ARGS:-} \
      "shiboken6_generator==$VERSION_PYSIDE" || {
    echo "ATTENTION : shiboken6_generator==$VERSION_PYSIDE non installe." >&2
    echo "            Sans lui, pas de binding : le panneau le dira." >&2
  }
  echo
  echo "--- Construction du binding QTermWidget ---"
  # build.sh refuse de compiler si le Qt des en-tetes (systeme) et le Qt du runtime
  # (celui de la roue PySide6) different de version mineure : il produirait un module
  # qui charge deux Qt dans le meme processus. Cet echec-la est NORMAL et non fatal.
  bash "/DATA/Python/FORKS/SmartPythonEditorPlugins/smartos_konsole/qtermwidget_binding/build.sh" "$SPYDER_PYTHON" || {
    echo "Binding non construit : le panneau du greffon dira quoi faire pour l'obtenir." >&2
  }
else
  echo "PySide6 absent de ce venv (PyQt6 ?) : pas de binding shiboken possible."
  echo "Le greffon s'installera, mais son panneau dira que le moteur manque."
fi

# --- Prerequis : le moteur de terminal partage -------------------------------
# smartos_konsole n'est pas un greffon mais une BIBLIOTHEQUE, importee par les deux
# panneaux a terminaux. Le prerequis est donc SYMETRIQUE — aucun greffon ne depend de
# l'autre — la ou le greffon Claude dependait autrefois du greffon Terminal.
echo
echo "--- Prerequis : moteur de terminal Konsole ---"
if ! "$SPYDER_PYTHON" -c "import smartos_konsole" 2>/dev/null; then
  echo "Moteur Konsole absent : installation prealable." >&2
  bash greffon_moteur_konsole || {
    echo "ERREUR : le moteur Konsole n'a pas pu etre installe." >&2
    echo "         Le panneau n'a alors ni terminal ni shell." >&2
    exit 1; }
fi
echo "Moteur Konsole present."

# --- Verification de chargement ----------------------------------------------
if [ "$SANS_TESTS" = false ]; then
  echo
  echo "--- Tests du greffon ---"
  # La mosaique : offscreen, sans Spyder ni moteur de terminal.
  QT_QPA_PLATFORM=offscreen "$SPYDER_PYTHON" "$PLUGIN_DIR/tests/test_mosaique.py" \
    || { echo "ERREUR : les tests de la mosaique echouent." >&2; exit 1; }
  # LE PANNEAU LUI-MEME, monte hors de Spyder. Ce banc n'existait pas avant le
  # 31/07/2026, et son absence avait laisse passer quatre defauts muets (cf. son en-tete).
  # C'est le seul qui eprouve la classe qui assemble tout le reste.
  QT_QPA_PLATFORM=offscreen "$SPYDER_PYTHON" "$PLUGIN_DIR/tests/test_panneau.py" \
    || { echo "ERREUR : les tests du panneau echouent." >&2; exit 1; }
fi

echo
echo "--- Chargement du greffon ---"
QT_QPA_PLATFORM=offscreen PYTHONPATH="$PLUGIN_DIR" "$SPYDER_PYTHON" -c "
from qtpy.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from spyder_native_terminal.spyder.plugin import TerminalNatif
assert TerminalNatif.NAME == 'native_terminal'

# L'INDEPENDANCE SE VERIFIE ICI, et c'est le seul endroit ou elle se verrait rompre : un
# import vers l'autre greffon reviendrait sans bruit a la premiere reprise de code entre
# les deux panneaux, qui sont jumeaux, et ne se remarquerait que le jour ou l'on
# installerait ce greffon seul. Le moteur partage, lui, est attendu.
import sys
assert not [m for m in sys.modules if m.startswith('spyder_claude')], \
    'ce greffon ne doit dependre d\'aucun autre greffon'

# L'icone est le seul element visible du greffon avant qu'on l'ouvre : un nom qtawesome
# invalide leve dans setup(), et Spyder AVALE cette exception - le greffon serait
# simplement absent du menu, sans un mot.
import qtawesome as qta
assert not qta.icon('mdi.console').isNull()
assert not qta.icon('mdi.console-line').isNull()

from smartos_konsole.konsole_view import DISPONIBLE
print('OK  greffon Terminal natif chargeable ; moteur Konsole :',
      'present' if DISPONIBLE else 'ABSENT (binding a construire)')
" || { echo "ERREUR : le greffon ne se charge pas - installation annulee." >&2; exit 1; }

# --- Installation ------------------------------------------------------------
echo
# ⚠ PAS de "pip install" ici : le venv pyenv de Spyder est construit a partir d'un
# requirements fige qui NE CONTIENT PAS setuptools (cf. l'en-tete de
# install_spyder_plugin.py).
python3 "$OUTIL_INSTALL" \
    "$PLUGIN_DIR" "$SPYDER_PYTHON" || {
  echo "ERREUR : l'installation du plugin a echoue." >&2; exit 1; }

echo
echo "Plugin 'Terminal natif' installe."
