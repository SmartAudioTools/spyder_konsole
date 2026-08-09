# -*- coding: utf-8 -*-
"""Greffon « Terminal natif » : un vrai terminal dans un dock, sans Chromium ni serveur.

Il remplit la meme fonction que le greffon amont `spyder-terminal` mais sans sa pile
(xterm.js + QWebEngineView + tornado + terminado + websocket) : l'emulateur est en
Python pur et le rendu est un QWidget. Cf. la note de conception dans
CachyOS/Documentation/TODO - Spyder - plugin Terminal.txt.

Le greffon est le SEUL a parler aux autres greffons de Spyder : il fournit au panneau le
repertoire du projet ouvert (ou, a defaut, celui du fichier en cours d'edition).
"""

import os

import qtawesome as qta

from spyder.api.plugins import Plugins, SpyderDockablePlugin
from spyder.utils.icon_manager import ima

from spyder_konsole.spyder.main_widget import PanneauTerminal
from spyder_konsole.spyder.translations import _


class TerminalNatif(SpyderDockablePlugin):
    """Panneau de terminaux."""

    NAME = "native_terminal"      # doit etre identique au nom du point d'entree
    REQUIRES = []
    OPTIONAL = [Plugins.WorkingDirectory]
    TABIFY = [Plugins.Console]
    WIDGET_CLASS = PanneauTerminal
    CONF_SECTION = "native_terminal"
    CONF_FILE = False

    @staticmethod
    def get_name():
        return _("Terminal natif")

    @staticmethod
    def get_description():
        return _("Terminal integre en Python pur : un shell dans un dock, sans "
                 "navigateur embarque ni serveur local.")

    @classmethod
    def get_icon(cls):
        return qta.icon("mdi.console", color=ima.MAIN_FG_COLOR)

    # --- API SpyderDockablePlugin --------------------------------------------

    def on_initialize(self):
        self.get_widget().sig_repertoire_demande.connect(self.ouvrir_terminal)

    def on_mainwindow_visible(self):
        """Ouvre une premiere session des que Spyder est affiche.

        Demande de l'utilisateur (26/07/2026) : un terminal doit etre la, pret, dans le
        repertoire courant — comme la console IPython, qui demarre elle aussi toute
        seule. On attend que la fenetre soit VISIBLE plutot que de le faire dans
        on_initialize : le repertoire de travail n'est pas encore etabli a ce moment-la,
        et le shell partirait dans le mauvais dossier.
        """
        widget = self.get_widget()
        # Apres tout le montage de Spyder : c'est le seul moment ou masquer le burger
        # vide tient (cf. PanneauTerminal._masquer_burger_vide).
        widget._masquer_burger_vide()
        if widget.nombre_de_sessions() == 0:
            self.ouvrir_terminal()

    def on_close(self, cancelable=False):
        # Le framework n'appelle pas toujours widget.on_close : on le declenche ici,
        # sinon les shells survivent a la fermeture de Spyder.
        self.get_widget().on_close()
        return True

    # --- API publique, utilisable depuis --gui-exec --------------------------

    def ouvrir_terminal(self, repertoire=None):
        """Ouvre une session. Sans argument, dans le dossier du projet courant.

        Methode PUBLIQUE et sans argument obligatoire a dessein : c'est elle qui permet
        de tester le greffon en autonomie, sans clic, par
        `spyder --gui-exec <script>` avec
        `main.get_plugin('native_terminal').ouvrir_terminal()`.
        """
        return self.get_widget().ouvrir_terminal(repertoire or self._repertoire_defaut())

    def _repertoire_defaut(self):
        """Le REPERTOIRE COURANT de Spyder — celui de la barre « Repertoire de travail ».

        Demande explicite de l'utilisateur (26/07/2026) : « la console ne doit pas
        s'ouvrir dans le dossier du fichier edite, mais dans le repertoire courant ».
        C'est le meme dossier que celui ou s'execute la console IPython, donc le
        terminal et la console parlent du meme endroit — ce qui est exactement ce qu'on
        attend en tapant une commande a cote d'un `%run`.

        Deux versions precedentes se sont trompees de source, faute d'avoir demande :
        la racine du projet ouvert (il n'y en avait aucun), puis le dossier du fichier
        edite. Le greffon `workingdir` est la seule reponse juste, et il existe toujours
        — les replis ne servent qu'a ne jamais echouer.
        """
        travail = self.get_plugin(Plugins.WorkingDirectory, error=False)
        if travail is not None:
            try:
                chemin = travail.get_workdir()
            except AttributeError:
                chemin = None
            if chemin and os.path.isdir(chemin):
                return chemin

        return os.getcwd()
