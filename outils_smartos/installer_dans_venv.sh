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
# Installe le greffon versionne dans ce depot (spyder_konsole/,
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
# Invocation : installation_SmartPythonEditor.sh --greffon konsole
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

# --- Binding qtermwidget -----------------------------------------------------
# Le moteur (konsole_view.py) vit DANS ce greffon depuis le 09/08/2026 (il etait dans un
# paquet smartos_konsole a part du 31/07 au 08/08 - fusion sur decision utilisateur, le
# greffon Claude le tire desormais en dependance) ; le binding natif, lui, se compile
# CONTRE le Qt du SYSTEME (QTermWidget est lie a qt6-base) : la roue PySide6 du venv doit
# etre de la MEME serie mineure que lui, sans quoi build.sh refuse (deux Qt dans un meme
# processus). Sur les machines SmartOS on ALIGNE donc la roue sur le Qt systeme puis on
# construit. C'est la moitie qui PRODUIT ce que spyder_qt_env.sh suppose present (il leve
# la borne haute de check_qt() quand la roue depasse la plage de Spyder) : faite a la main
# le 26/07/2026, jamais scriptee, elle a ete perdue a la recreation du venv le 08/08/2026
# - panneaux Terminal et Claude ouverts sur « moteur non construit ». Retour arriere :
# pip install PySide6==<plage du fork>, et spyder_qt_env.sh redevient inerte de lui-meme.
if ! QT_QPA_PLATFORM=offscreen "$SPYDER_PYTHON" -c "import qtermwidget" 2>/dev/null; then
  # Prerequis systeme (Arch) : la bibliotheque C++ QTermWidget, et libxml2 en 2.x - le
  # generateur shiboken6 est lie a libxml2.so.2, disparu d'Arch (diagnostic du 26/07/2026 :
  # son message d'erreur ne dit pas quel paquet installer). Echec non fatal : hors Arch ou
  # sans sudo, le controle des en-tetes ci-dessous dira quoi installer.
  if command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm qtermwidget libxml2-legacy || {
      echo "ATTENTION : installation de qtermwidget/libxml2-legacy impossible." >&2
    }
  fi
  QT_SYSTEME="$(pkg-config --modversion Qt6Core 2>/dev/null || true)"
  if [ -z "$QT_SYSTEME" ] || { ! pkg-config --exists qtermwidget6 2>/dev/null \
       && [ ! -f /usr/include/qtermwidget6/qtermwidget.h ]; }; then
    echo
    echo "ATTENTION : binding qtermwidget non construit, et en-tetes Qt6/QTermWidget absents" >&2
    echo "            (paquets qt6-base + qtermwidget). Les installer puis relancer" >&2
    echo "            $PLUGIN_DIR/qtermwidget_binding/build.sh," >&2
    echo "            sinon les panneaux Terminal et Claude s'ouvriront sur un message" >&2
    echo "            d'attente au lieu d'un shell." >&2
  else
    PYSIDE_VENV="$("$SPYDER_PYTHON" -c 'from PySide6 import __version__; print(__version__)')"
    if [ "${PYSIDE_VENV%.*}" != "${QT_SYSTEME%.*}" ]; then
      echo
      echo "--- Alignement de PySide6 ($PYSIDE_VENV) sur le Qt systeme ($QT_SYSTEME) ---"
      # ==<majeur.mineur>.* et pas ==$QT_SYSTEME : les correctifs (troisieme chiffre) de la
      # roue et du paquet systeme divergent couramment, seule la serie mineure compte.
      "$SPYDER_PYTHON" -m pip install ${PIP_CACHE_ARGS:-} \
          "PySide6==${QT_SYSTEME%.*}.*" "PySide6_Essentials==${QT_SYSTEME%.*}.*" \
          "PySide6_Addons==${QT_SYSTEME%.*}.*" "shiboken6==${QT_SYSTEME%.*}.*" \
          "shiboken6_generator==${QT_SYSTEME%.*}.*" || {
        echo "ERREUR : alignement de PySide6 sur Qt $QT_SYSTEME impossible." >&2; exit 1; }
    else
      # Meme serie : seul le generateur (absent des requirements) peut manquer pour compiler.
      "$SPYDER_PYTHON" -m pip install ${PIP_CACHE_ARGS:-} \
          "shiboken6_generator==${PYSIDE_VENV%.*}.*" || {
        echo "ERREUR : installation de shiboken6_generator impossible." >&2; exit 1; }
    fi
    bash "$PLUGIN_DIR/qtermwidget_binding/build.sh" "$SPYDER_PYTHON" || {
      echo "ERREUR : construction du binding qtermwidget echouee (voir ci-dessus)." >&2
      exit 1; }
    QT_QPA_PLATFORM=offscreen "$SPYDER_PYTHON" -c "import qtermwidget" || {
      echo "ERREUR : binding construit mais toujours pas importable." >&2; exit 1; }
    echo "Binding qtermwidget construit et verifie."
  fi
fi

# --- Verification de chargement ----------------------------------------------
if [ "$SANS_TESTS" = false ]; then
  echo
  echo "--- Tests du greffon ---"
  # Le moteur : de vrais shells et de vraies frappes (QTest), cas sautes si le binding
  # n'est pas construit. Vivait dans le paquet smartos_konsole jusqu'au 09/08/2026.
  QT_QPA_PLATFORM=offscreen "$SPYDER_PYTHON" "$PLUGIN_DIR/tests/test_konsole_view.py" \
    || { echo "ERREUR : les tests du moteur Konsole echouent." >&2; exit 1; }
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

from spyder_konsole.spyder.plugin import TerminalNatif
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

from spyder_konsole.konsole_view import DISPONIBLE
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
