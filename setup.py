"""Construit le binding QTermWidget pendant l'installation pip.

POURQUOI UN setup.py A COTE DU pyproject.toml
  Ce greffon est du Python pur SAUF son moteur : QTermWidget est une bibliotheque C++ du
  SYSTEME, atteinte par un binding shiboken6 qui ne peut pas etre livre construit. Il se lie
  a la fois au Qt du systeme et a la serie mineure exacte de la roue PySide6 du venv - les
  deux sont inscrites dans le nom des bibliotheques qu'il charge (libpyside6.abi3.so.6.11,
  libqtermwidget6.so.2), donc une roue pre-construite ne vaudrait que pour une combinaison
  (serie PySide6 x soname QTermWidget x architecture) a la fois. Il se compile sur la machine
  cible, ou nulle part.

  Ce fichier branche donc cette construction sur le geste standard « pip install [-e] », pour
  que le greffon tienne en UNE LIGNE de requirements comme les dix autres, au lieu d'un
  installeur qui lui soit propre. Le comment de la construction reste entier dans
  qtermwidget_binding/build.sh : ce fichier ne fait que l'appeler au bon moment.

⚠ EXIGE --no-build-isolation
  build.sh depose le binding dans le site-packages de l'interpreteur qui construit. Sous
  isolation de build, cet interpreteur est un venv temporaire jete aussitot apres : le
  binding partirait avec lui. C'est la raison pour laquelle setuptools figure dans le
  requirements du venv Spyder - sans lui dans le venv, --no-build-isolation ne peut pas
  construire du tout.

⚠ UN ECHEC DE CONSTRUCTION N'EST PAS UN ECHEC D'INSTALLATION
  Sans les paquets systeme (qtermwidget, qt6-base), ou avec une roue PySide6 qui n'est pas
  dans la serie du Qt systeme, build.sh s'arrete en NOMMANT ce qui manque - et l'installation
  continue quand meme. Le greffon s'installe alors sans moteur et affiche dans son panneau ce
  qu'il faut faire. C'est deliberement dissymetrique : un greffon qui refuse de s'installer
  disparait de la liste des greffons de Spyder, et plus personne ne sait pourquoi.
"""

import os
import subprocess
import sys

from setuptools import setup
from setuptools.command.build_py import build_py

ICI = os.path.dirname(os.path.abspath(__file__))
BUILD_SH = os.path.join(ICI, "qtermwidget_binding", "build.sh")


class ConstruireLeBinding(build_py):
    """Lance build.sh avant la copie des sources Python.

    Accroche sur build_py et non sur build_ext : le binding n'est pas une Extension
    setuptools (shiboken genere ses sources lui-meme, puis les compile avec ses propres
    options), et build_ext ne tourne pas quand ext_modules est vide - y compris en
    installation editable.
    """

    def run(self):
        # Pas d'interrupteur pour sauter la construction : build.sh sort deja proprement, en
        # nommant ce qui manque, sur une machine sans les en-tetes Qt ou QTermWidget - c'est
        # exactement le cas qu'un tel interrupteur aurait servi a couvrir.
        try:
            subprocess.run(["bash", BUILD_SH, sys.executable], check=True)
        except (subprocess.CalledProcessError, OSError) as erreur:
            # Volontairement non fatal : cf. l'en-tete de ce fichier.
            print("\nATTENTION : binding QTermWidget non construit (%s)." % erreur,
                  file=sys.stderr)
            print("            Le greffon s'installe quand meme ; son panneau dira quoi "
                  "faire.\n", file=sys.stderr)
        super().run()


setup(cmdclass={"build_py": ConstruireLeBinding})
