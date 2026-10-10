# -*- coding: utf-8 -*-
"""Le PANNEAU lui-meme, monte hors de Spyder.

CE BANC N'EXISTAIT PAS, et c'est ce qui a laisse passer trois defauts pendant toute la
campagne mosaique du 27 au 31/07/2026. Les bancs precedents couvraient la mosaique et le
moteur Konsole — deux modules sans dependance a Spyder, donc faciles a eprouver — mais
jamais la classe qui les assemble. Les trois defauts vivaient exactement la, et aucun ne
se voyait a l'ecran :

  1. `ACTION_AGRANDIR` n'etait defini que dans la sous-classe Claude. Le panneau Terminal
     lisait donc `self.ACTION_AGRANDIR` sur une classe qui ne l'a pas — dans un
     `try/except Exception` qui rendait None, donc en silence. Son bouton de reduction
     retombait sur le repli, celui-la meme qui produit l'etat intermediaire que
     l'utilisateur avait signale le 27/07 (« on est oblige de reduire deux fois »).
  2. `ouvrir_terminal` n'ajoutait rien a `self._vues`. Seule la surcharge de Claude le
     faisait. Or `_ajuster_affichage` decide d'etaler ou non sur `bool(self._vues)` : la
     mosaique du panneau Terminal ne pouvait donc JAMAIS s'afficher.
  3. `QTimer` n'etait pas importe au niveau du module, alors que la pose differee du
     bouton de disposition l'utilise. Chemin rarement pris — il ne sert que si le coin
     n'existe pas encore — donc une NameError qui attendait son jour.

Les trois sont invisibles a l'oeil et evidents ici. C'est la raison d'etre du fichier.

POURQUOI CE BANC PEUT EXISTER, alors qu'un widget de greffon semble exiger Spyder complet :
il suffit que la classe porte un `CONF_SECTION`, seule chose que reclame le mixin de
configuration. Le panneau accepte `plugin=None` — il ne va jamais chercher dans le registre
des greffons, c'est precisement le decoupage qui le rend testable.

⚠ AUCUNE SESSION N'EST OUVERTE ICI. `ouvrir_terminal` lance un vrai shell sur un vrai pty ;
on ne veut ni la lenteur ni les processus orphelins dans un banc. On monte donc de fausses
vues, ce qui suffit : les defauts cherches sont dans la mecanique du panneau, pas dans le
moteur — lui a deja son banc.
"""

import os
import sys
import unittest
import warnings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qtpy.QtWidgets import QApplication, QWidget  # noqa: E402

APP = QApplication.instance() or QApplication([])

from spyder_konsole.spyder.main_widget import PanneauTerminal  # noqa: E402

# Monter plusieurs panneaux dans le meme processus fait rouspeter le registre de Spyder :
# chaque instance reenregistre ses boutons sous les memes identifiants. C'est attendu ici —
# hors banc, il n'y a qu'un panneau par greffon — et cinquante lignes d'avertissement
# noieraient le resultat des tests.
#
# ⚠ POSE APRES L'IMPORT DE SPYDER, ET PAS AVANT : Spyder repose ses propres filtres
# a l'import, ce qui effacait celui-ci (mesure du 31/07/2026 — filtre en tete de
# fichier, cinquante avertissements quand meme).
warnings.filterwarnings("ignore", message=r"There already exists a reference")



class Banc(PanneauTerminal):
    """Le panneau reel, a un attribut pres : celui qu'exige le mixin de configuration."""

    CONF_SECTION = "native_terminal"


class FausseVue(QWidget):
    """Ce que le panneau attend d'une vue, et rien de plus."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.arrets = []

    def arreter(self, force=False):
        self.arrets.append(force)

    def poser_liseret(self, couleur):
        self._liseret = couleur


def panneau():
    p = Banc(name="native_terminal", plugin=None, parent=None)
    p.setup()
    return p


class TestMontage(unittest.TestCase):
    """Ce que le panneau doit porter pour que ses propres methodes fonctionnent."""

    def setUp(self):
        self.p = panneau()

    def tearDown(self):
        self.p.deleteLater()

    def test_setup_ne_leve_pas(self):
        """DEFAUT 3 : la pose differee du bouton de disposition utilise QTimer.

        Sans l'import au niveau du module, `setup()` leve NameError des que le coin des
        onglets n'existe pas encore — ce qui est le cas ici, et l'est aussi dans Spyder
        selon le moment ou le panneau est monte.
        """
        self.assertIsNotNone(self.p._bouton_disposition)

    def test_action_agrandir_est_definie(self):
        """DEFAUT 1 : lue par `_action_agrandissement`, elle doit exister sur CETTE classe.

        On la cherche dans le dictionnaire de la classe et de ses parents jusqu'a
        PluginMainWidget exclu : `getattr` seul serait satisfait par un attribut herite
        d'une sous-classe, ce qui est exactement le defaut d'origine.
        """
        self.assertTrue(
            any("ACTION_AGRANDIR" in c.__dict__
                for c in type(self.p).__mro__
                if c.__module__.startswith("spyder_konsole")),
            "ACTION_AGRANDIR doit etre definie par le greffon lui-meme")
        self.assertIsInstance(self.p.ACTION_AGRANDIR, str)

    def test_action_agrandissement_ne_leve_pas(self):
        """Hors Spyder l'action est introuvable ; la methode doit rendre None, pas lever."""
        self.assertIsNone(self.p._action_agrandissement())


class TestListeDesSessions(unittest.TestCase):
    """`_vues` est le seul etat vrai dans les deux modes ; tout en depend."""

    def setUp(self):
        self.p = panneau()

    def tearDown(self):
        self.p.deleteLater()

    def _ouvrir(self, titre="essai"):
        """Reproduit ce que fait `ouvrir_terminal` APRES la creation de la vue.

        On ne l'appelle pas : elle lance un vrai shell. Ce qui est teste ici est
        l'invariant qu'elle doit tenir, pas le moteur.
        """
        vue = FausseVue(self.p._onglets)
        self.p._onglets.addTab(vue, titre)
        self.p._vues.append(vue)
        self.p._titres[vue] = titre
        return vue

    def test_ouvrir_terminal_alimente_les_vues(self):
        """DEFAUT 2 : sans cette ligne, la mosaique du panneau ne s'affiche jamais.

        On lit la SOURCE de la methode plutot que de l'executer, faute de pouvoir lancer
        un shell dans un banc. C'est une verification faible en soi — mais elle porte sur
        la ligne exacte dont l'absence a rendu la mosaique inatteignable, et elle echoue
        bien si on la retire.
        """
        import inspect
        source = inspect.getsource(PanneauTerminal.ouvrir_terminal)
        self.assertIn("self._vues.append(vue)", source)

    def test_nombre_de_sessions_ignore_longlet_dattente(self):
        """L'onglet d'attente n'est pas une session : le greffon en ouvrirait zero.

        `on_mainwindow_visible` n'ouvre une session que si le compte est nul. Compter les
        ONGLETS le rendait non nul des qu'un onglet d'attente etait affiche — donc un
        panneau qui reste vide.
        """
        self.p._etat_vide("rien ici")
        self.assertEqual(self.p._onglets.count(), 1)
        self.assertEqual(self.p.nombre_de_sessions(), 0)

    def test_nombre_de_sessions_compte_en_mosaique(self):
        """En mosaique la barre d'onglets est vide : compter les onglets rendrait zero."""
        self._ouvrir()
        self._ouvrir()
        self.p._passer_en_mosaique()
        self.assertEqual(self.p._onglets.count(), 0)
        self.assertEqual(self.p.nombre_de_sessions(), 2)

    def test_oublier_purge_la_vue(self):
        vue = self._ouvrir()
        self.p._oublier(vue)
        self.assertNotIn(vue, self.p._vues)
        self.assertNotIn(vue, self.p._titres)


class TestBascule(unittest.TestCase):
    """Aller-retour mosaique / onglets, sans passer par Spyder."""

    def setUp(self):
        self.p = panneau()
        self.vues = []
        for titre in ("un", "deux"):
            vue = FausseVue(self.p._onglets)
            self.p._onglets.addTab(vue, titre)
            self.p._vues.append(vue)
            self.p._titres[vue] = titre
            self.vues.append(vue)

    def tearDown(self):
        self.p.deleteLater()

    def test_agrandir_etale_puis_reduire_rassemble(self):
        self.p.set_maximized_state(True)
        self.assertTrue(self.p.en_mosaique())
        self.assertEqual(self.p._onglets.count(), 0)

        self.p.set_maximized_state(False)
        self.assertFalse(self.p.en_mosaique())
        self.assertEqual(self.p._onglets.count(), 2)

    def test_les_vues_survivent_a_laller_retour(self):
        """La bascule DEPLACE les vues ; elle n'en detruit ni n'en recree aucune."""
        avant = list(self.p._vues)
        self.p.set_maximized_state(True)
        self.p.set_maximized_state(False)
        self.assertEqual(self.p._vues, avant)

    def test_bouton_de_disposition_visible_seulement_agrandi_en_onglets(self):
        """Il proposerait sinon un etat inatteignable, ou serait cache par la mosaique.

        ⚠ ON LIT `isHidden()`, PAS `isVisible()`. Un widget dont aucun ancetre n'est
        affiche est toujours `isVisible() == False`, et le panneau d'un banc n'est jamais
        montre a l'ecran : l'assertion aurait ete verte quoi qu'il arrive — un test qui ne
        peut pas echouer, donc qui ne prouve rien.
        """
        self.assertTrue(self.p._bouton_disposition.isHidden())
        self.p.set_maximized_state(True)          # agrandi -> mosaique : masque
        self.assertTrue(self.p._bouton_disposition.isHidden())
        self.p._basculer_disposition()            # agrandi -> onglets : visible
        self.assertFalse(self.p.en_mosaique())
        self.assertFalse(self.p._bouton_disposition.isHidden())

    def test_la_preference_survit_a_lagrandissement(self):
        """Sans `_mosaique_voulue`, le retour aux onglets serait aussitot annule."""
        self.p.set_maximized_state(True)
        self.p._basculer_disposition()
        self.p._ajuster_affichage()
        self.assertFalse(self.p.en_mosaique())


class TestFermeture(unittest.TestCase):

    def setUp(self):
        self.p = panneau()

    def tearDown(self):
        self.p.deleteLater()

    def test_on_close_arrete_les_sessions_en_mosaique(self):
        """⚠ ON PARCOURT LES SESSIONS, PAS LES ONGLETS.

        En mosaique la barre est vide : une boucle sur les onglets ne fermerait rien, et
        les shells survivraient a la fermeture de Spyder.
        """
        vues = []
        for titre in ("un", "deux"):
            vue = FausseVue(self.p._onglets)
            self.p._onglets.addTab(vue, titre)
            self.p._vues.append(vue)
            self.p._titres[vue] = titre
            vues.append(vue)
        self.p._passer_en_mosaique()
        self.assertEqual(self.p._onglets.count(), 0)

        self.p.on_close()
        for vue in vues:
            self.assertEqual(vue.arrets, [True], "session non arretee")


if __name__ == "__main__":
    # ⚠ PAS `unittest.main()` : il repose les filtres d'avertissement au demarrage
    # (`simplefilter("default")` des que `sys.warnoptions` est vide), ce qui EFFACE celui
    # pose plus haut — les cinquante lignes du registre de Spyder revenaient donc noyer le
    # resultat. `TextTestRunner`, lui, ne touche aux filtres que si on le lui demande.
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    resultat = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if resultat.wasSuccessful() else 1)
