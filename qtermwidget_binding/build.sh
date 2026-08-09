#!/usr/bin/env bash
# Construit le binding Python de QTermWidget (le moteur terminal de Konsole) pour le
# PySide6 du venv Spyder, puis l'installe dans ce venv.
#
# Ni root ni reseau : tout ce qui devait etre installe l'est deja (paquet qtermwidget,
# roue shiboken6_generator). Le script echoue BRUYAMMENT et nomme le paquet manquant si
# ce n'est pas le cas — un binding a moitie construit est pire que pas de binding.
#
# Usage :
#     bash qtermwidget_binding/build.sh [chemin/du/python/du/venv]
#
# Il est REJOUABLE : chaque montee de PySide6 ou de Qt demande de le relancer, c'est le
# cout assume de cette voie (cf. TODO - Spyder - plugin Terminal.txt).

set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${1:-/DATA/Python/SmartPython/CachyOS/versions/SmartPythonEditor/bin/python}"
CONSTRUCTION="${QTERMWIDGET_BUILD_DIR:-$ICI/build}"

# Emplacements des en-tetes systeme, detectes plutot que codes en dur (08/08/2026,
# distribution SmartPythonEditor : ce script tourne desormais aussi hors Arch). pkg-config
# fait foi quand il repond ; sinon repli sur les chemins connus, Arch puis Debian/Ubuntu.
detecter_includedir() {  # detecter_includedir <module pkg-config> <repli>...
    local module="$1" ; shift
    local dir
    dir="$(pkg-config --variable=includedir "$module" 2>/dev/null || true)"
    if [ -n "$dir" ] && [ -d "$dir" ]; then echo "$dir"; return; fi
    for dir in "$@"; do
        if [ -d "$dir" ]; then echo "$dir"; return; fi
    done
    echo ""
}
DIR_QT="$(detecter_includedir Qt6Core /usr/include/qt6 "/usr/include/$(uname -m)-linux-gnu/qt6")"
# Le .pc de QTermWidget ne donne que le includedir parent : son sous-dossier porte le nom
# du paquet, identique sur Arch et Debian.
DIR_QTERMWIDGET=""
for d in "${DIR_QT:+$DIR_QT/../qtermwidget6}" /usr/include/qtermwidget6 \
         "/usr/include/$(uname -m)-linux-gnu/qtermwidget6"; do
    [ -n "$d" ] && [ -f "$d/qtermwidget.h" ] && DIR_QTERMWIDGET="$(cd "$d" && pwd)" && break
done

echo "== Binding QTermWidget pour PySide6 =="
echo "python : $PYTHON"

[ -x "$PYTHON" ] || { echo "ECHEC : python introuvable : $PYTHON" >&2; exit 1; }

SITE="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
PYSIDE="$SITE/PySide6"
SHIBOKEN="$SITE/shiboken6"
GENERATEUR="$SITE/shiboken6_generator"
# Les en-tetes de shiboken ont change de roue au fil des versions : sous shiboken6/include
# autrefois, sous shiboken6_generator/include en 6.8.3 (constate le 08/08/2026 sur un venv
# neuf). On prend le premier existant.
SHIBOKEN_INCLUDE="$SHIBOKEN/include"
[ -f "$SHIBOKEN_INCLUDE/sbkpython.h" ] || SHIBOKEN_INCLUDE="$GENERATEUR/include"
INCLUDE_PYTHON="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')"

# --------------------------------------------------------------- prerequis

manque=0
verifier() {  # verifier <chemin> <message si absent>
    if [ ! -e "$1" ]; then
        echo "MANQUE : $2" >&2
        manque=1
    fi
}

verifier "${DIR_QTERMWIDGET:-/usr/include/qtermwidget6}/qtermwidget.h" \
    "les en-tetes de QTermWidget -> paquet 'qtermwidget' (pacman) / 'libqtermwidget6-dev' (apt)"
verifier "${DIR_QT:-/usr/include/qt6}/QtCore" \
    "les en-tetes de Qt6 -> paquet 'qt6-base' (pacman) / 'qt6-base-dev' (apt)"
verifier "$GENERATEUR/shiboken6" \
    "le generateur -> pip install shiboken6_generator==<version de PySide6>"
verifier "$PYSIDE/typesystems/typesystem_widgets.xml" \
    "les typesystems de PySide6 (roue pyside6 incomplete ?)"
verifier "$SHIBOKEN_INCLUDE/sbkpython.h" \
    "les en-tetes de shiboken (roue shiboken6 incomplete ?)"
verifier "$INCLUDE_PYTHON/Python.h" \
    "les en-tetes de Python du venv"
[ "$manque" -eq 0 ] || { echo "ECHEC : prerequis manquants (voir ci-dessus)." >&2; exit 1; }

# Le generateur est un binaire C++ lie a libclang ET a libxml2/libxslt en version 2.x.
# Sur une Arch a jour, libxml2 est en soname .16 : le binaire ne demarre pas et le
# message d'erreur ("libxml2.so.2: cannot open shared object file") ne dit pas quel
# paquet installer. On le teste ICI, une fois, et on le dit clairement.
if ! "$GENERATEUR/shiboken6" --version >/dev/null 2>"$CONSTRUCTION.erreur" ; then
    if grep -q "libxml2.so.2" "$CONSTRUCTION.erreur" 2>/dev/null; then
        echo "ECHEC : le generateur shiboken6 exige libxml2 en version 2.x." >&2
        echo "        Sur cette machine libxml2 est en .16 ; le paquet de compatibilite" >&2
        echo "        existe dans les depots et s'installe en une commande (root) :" >&2
        echo "            sudo pacman -S --needed libxml2-legacy" >&2
    else
        echo "ECHEC : le generateur shiboken6 ne demarre pas :" >&2
        cat "$CONSTRUCTION.erreur" >&2
    fi
    rm -f "$CONSTRUCTION.erreur"
    exit 1
fi
rm -f "$CONSTRUCTION.erreur"

# Le Qt des EN-TETES (systeme) et le Qt du RUNTIME (celui de la roue PySide6) doivent
# etre de meme version : c'est exactement le mur d'ABI qui bloquait cette voie tant que
# la roue etait en 6.8.3 face a un qt6-base 6.11.1. On refuse de compiler si l'ecart
# revient, plutot que de produire un module qui plantera a l'execution.
QT_SYSTEME="$(pkg-config --modversion Qt6Core 2>/dev/null || true)"
QT_ROUE="$("$PYTHON" -c 'from PySide6 import __version__; print(__version__)')"
echo "Qt des en-tetes (systeme) : ${QT_SYSTEME:-inconnu}"
echo "Qt du runtime (PySide6)   : $QT_ROUE"
if [ -n "$QT_SYSTEME" ] && [ "${QT_SYSTEME%.*}" != "${QT_ROUE%.*}" ]; then
    echo "ECHEC : les versions mineures different (${QT_SYSTEME} vs ${QT_ROUE})." >&2
    echo "        Compiler contre des en-tetes d'une autre version mineure produit un" >&2
    echo "        module qui charge deux Qt dans le meme processus. Aligner d'abord." >&2
    exit 1
fi

# --------------------------------------------------------------- generation

rm -rf "$CONSTRUCTION"
mkdir -p "$CONSTRUCTION"

INCLUDES_QT="$DIR_QT"
for module in QtCore QtGui QtWidgets; do
    INCLUDES_QT="$INCLUDES_QT:$DIR_QT/$module"
done

echo "-- generation des sources (shiboken6)…"
"$GENERATEUR/shiboken6" \
    --generator-set=shiboken \
    --enable-pyside-extensions \
    --enable-parent-ctor-heuristic \
    --enable-return-value-heuristic \
    --use-isnull-as-nb-bool \
    --avoid-protected-hack \
    --typesystem-paths="$PYSIDE/typesystems" \
    --include-paths="$INCLUDES_QT:$DIR_QTERMWIDGET:/usr/include" \
    --output-directory="$CONSTRUCTION" \
    "$ICI/bindings.h" "$ICI/bindings.xml"

SOURCES=$(find "$CONSTRUCTION" -name "*.cpp" | sort)
[ -n "$SOURCES" ] || { echo "ECHEC : shiboken n'a genere aucune source." >&2; exit 1; }
echo "-- $(echo "$SOURCES" | wc -l) fichiers generes"

# --------------------------------------------------------------- compilation

COMPILATEUR="${CXX:-g++}"
command -v "$COMPILATEUR" >/dev/null || COMPILATEUR=clang++

# Les roues n'installent PAS les liens symboliques `libpyside6.abi3.so` : seul le nom
# versionne existe (…so.6.11). `-lpyside6.abi3` echoue donc, et il faut donner le chemin
# complet du fichier. On le resout ici plutot que de le coder en dur : il change a chaque
# montee de PySide6.
LIB_PYSIDE="$(ls "$PYSIDE"/libpyside6.abi3.so* 2>/dev/null | head -1)"
LIB_SHIBOKEN="$(ls "$SHIBOKEN"/libshiboken6.abi3.so* 2>/dev/null | head -1)"
[ -n "$LIB_PYSIDE" ] && [ -n "$LIB_SHIBOKEN" ] || {
    echo "ECHEC : bibliotheques libpyside6/libshiboken6 introuvables dans le venv." >&2
    exit 1
}

echo "-- compilation ($COMPILATEUR)…"
# -fvisibility=hidden : impose par les macros de shiboken, sans quoi les symboles des
# wrappers entrent en collision avec ceux de PySide6.
"$COMPILATEUR" -std=c++17 -fPIC -shared -O2 -fvisibility=hidden \
    -DNDEBUG \
    -I"$ICI" \
    -I"$CONSTRUCTION/qtermwidget" \
    -I"$INCLUDE_PYTHON" \
    -I"$SHIBOKEN_INCLUDE" \
    -I"$PYSIDE/include" \
    -I"$PYSIDE/include/QtCore" \
    -I"$PYSIDE/include/QtGui" \
    -I"$PYSIDE/include/QtWidgets" \
    -I"$DIR_QTERMWIDGET" \
    -I"$DIR_QT" \
    -I"$DIR_QT/QtCore" \
    -I"$DIR_QT/QtGui" \
    -I"$DIR_QT/QtWidgets" \
    $SOURCES \
    "$LIB_PYSIDE" "$LIB_SHIBOKEN" \
    -lqtermwidget6 -lQt6Widgets -lQt6Gui -lQt6Core \
    -Wl,-rpath,"$PYSIDE" -Wl,-rpath,"$SHIBOKEN" -Wl,-rpath,"$PYSIDE/Qt/lib" \
    -o "$CONSTRUCTION/qtermwidget.abi3.so"

# --------------------------------------------------------------- installation

install -m 644 "$CONSTRUCTION/qtermwidget.abi3.so" "$SITE/qtermwidget.abi3.so"
echo "-- installe : $SITE/qtermwidget.abi3.so"

# --------------------------------------------------------------- verification

echo "-- verification (import + instanciation offscreen)…"
QT_QPA_PLATFORM=offscreen "$PYTHON" - <<'VERIF'
import sys
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
import qtermwidget
widget = qtermwidget.QTermWidget(0)
widget.setShellProgram("/bin/sh")
widget.setArgs(["-c", "true"])
print("   QTermWidget instancie :", widget.metaObject().className())
print("   jeux de couleurs disponibles :", len(widget.availableColorSchemes()))
VERIF

echo "== Termine =="
