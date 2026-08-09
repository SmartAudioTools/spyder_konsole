# -*- coding: utf-8 -*-
"""Tests du moteur QTermWidget — en OFFSCREEN, sans Spyder et sans un seul clic.

Ce que ces tests prouvent, et qu'aucune lecture de code ne prouve : que le binding
shiboken produit un widget qui charge, qui lance reellement un shell, dont la sortie
arrive a l'ecran du terminal, et qui meurt proprement. C'est la difference entre « le
module s'importe » et « le terminal fonctionne ».

Ils tournent en `QT_QPA_PLATFORM=offscreen` : c'est sans danger ici, contrairement au
lancement de SPYDER en offscreen (qui reecrit la disposition des docks de l'utilisateur
en se fermant) — on n'instancie qu'un widget isole, aucune configuration n'est touchee.

Lancement :
    QT_QPA_PLATFORM=offscreen <python du venv Spyder> tests/test_konsole_view.py
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qtpy.QtCore import QEventLoop, QTimer  # noqa: E402
from qtpy.QtWidgets import QApplication  # noqa: E402

from spyder_konsole.konsole_view import DISPONIBLE  # noqa: E402


APPLICATION = QApplication.instance() or QApplication(sys.argv)


def attendre(condition, delai_max_ms=10000):
    """Attend qu'une condition devienne vraie SANS sleep fixe.

    La charge de cette machine monte quand plusieurs instances travaillent : tout delai
    calibre au repos devient faux. On sonde l'etat reel et on borne l'attente.
    """
    boucle = QEventLoop()
    ecoule = {"ms": 0}

    def verifier():
        ecoule["ms"] += 50
        if condition() or ecoule["ms"] >= delai_max_ms:
            boucle.quit()

    minuteur = QTimer()
    minuteur.timeout.connect(verifier)
    minuteur.start(50)
    boucle.exec_() if hasattr(boucle, "exec_") else boucle.exec()
    minuteur.stop()
    return condition()


@unittest.skipUnless(DISPONIBLE, "binding qtermwidget non construit")
class BaseTerminal(unittest.TestCase):
    """Une session de terminal montee et demontee pour chaque test.

    Le montage etait recopie dans chacune des classes de tests, `self.contenu()` compris.
    Le factoriser retire une soixantaine de lignes et surtout une source d'erreur : une
    selection oubliee dans une copie fausse silencieusement le test.
    """

    def setUp(self):
        from spyder_konsole.konsole_view import VueKonsole
        self.vue = VueKonsole(couleur_fond="#19232D", couleur_texte="#DFE1E2")
        self.vue.resize(600, 300)
        self.vue.show()

    def tearDown(self):
        self.vue.arreter(force=True)
        self.vue.deleteLater()
        APPLICATION.processEvents()

    def contenu(self):
        """Tout l'ecran, en texte. QTermWidget n'expose son contenu que par la selection."""
        terminal = self.vue._terminal
        terminal.setSelectionStart(0, 0)
        terminal.setSelectionEnd(terminal.screenLinesCount() - 1,
                                 terminal.screenColumnsCount() - 1)
        return terminal.selectedText(True)

    def attendre_le_shell(self):
        self.assertTrue(attendre(lambda: self.vue._terminal.getShellPID() > 0))
        return self.vue._terminal.getShellPID()

    def attendre_a_l_ecran(self, marqueur):
        self.assertTrue(attendre(lambda: marqueur in self.contenu()),
                        "%s n'est jamais arrive a l'ecran" % marqueur)


class TestVueKonsole(BaseTerminal):
    """Le moteur de Konsole, pilote depuis Python."""

    def test_shell_demarre_et_expose_son_pid(self):
        self.vue.demarrer(commande=["/bin/sh"])
        self.assertTrue(attendre(lambda: self.vue._terminal.getShellPID() > 0))
        pid = self.vue._terminal.getShellPID()
        self.assertGreater(pid, 0)
        # Le pid doit exister VRAIMENT : un entier non nul ne prouve rien.
        os.kill(pid, 0)

    def test_la_sortie_du_shell_arrive_a_l_ecran(self):
        """Le test qui compte : ce que la commande ecrit doit etre LU dans le terminal."""
        self.vue.demarrer(commande=["/bin/sh", "-c", "echo MARQUEUR_SMARTOS; sleep 5"])
        terminal = self.vue._terminal

        self.assertTrue(attendre(lambda: "MARQUEUR_SMARTOS" in self.contenu()),
                        "la sortie du shell n'est jamais arrivee a l'ecran")

    def test_envoi_de_texte_execute_la_commande(self):
        """sendText simule la frappe : c'est ainsi qu'on pilote le terminal sans clic."""
        self.vue.demarrer(commande=["/bin/sh"])
        self.assertTrue(attendre(lambda: self.vue._terminal.getShellPID() > 0))
        terminal = self.vue._terminal
        self.vue.envoyer("echo PILOTE_SANS_CLIC\n")

        self.assertTrue(attendre(lambda: "PILOTE_SANS_CLIC" in self.contenu()))

    def test_fin_du_shell_emet_le_signal(self):
        fini = {"oui": False}
        self.vue.sig_termine.connect(lambda _code: fini.__setitem__("oui", True))
        self.vue.demarrer(commande=["/bin/sh", "-c", "exit 0"])
        self.assertTrue(attendre(lambda: fini["oui"]),
                        "sig_termine n'a pas ete emis a la sortie du shell")

    def test_arreter_tue_le_shell_lance_par_cette_vue(self):
        self.vue.demarrer(commande=["/bin/sh", "-c", "sleep 30"])
        self.assertTrue(attendre(lambda: self.vue._terminal.getShellPID() > 0))
        pid = self.vue._terminal.getShellPID()
        self.vue.arreter(force=True)

        def mort():
            try:
                os.kill(pid, 0)
            except OSError:
                return True
            return False

        self.assertTrue(attendre(mort), "le shell survit a arreter(force=True)")

    def test_environnement_transmis_au_shell(self):
        """Le marqueur d'introspection doit exister DANS le shell, pas seulement en Python."""
        self.vue.demarrer(commande=[
            "/bin/sh", "-c", "echo MOTEUR=$SPYDER_NATIVE_TERMINAL; sleep 5"])
        terminal = self.vue._terminal

        self.assertTrue(attendre(lambda: "MOTEUR=1" in self.contenu()))

    def test_repertoire_de_travail_respecte(self):
        self.vue.demarrer(commande=["/bin/sh", "-c", "pwd; sleep 5"],
                          repertoire="/DATA/Python/SmartOS")
        terminal = self.vue._terminal

        self.assertTrue(attendre(lambda: "/DATA/Python/SmartOS" in self.contenu()))

    def test_jeux_de_couleurs_de_konsole_disponibles(self):
        """Preuve que c'est bien le moteur de Konsole : ses jeux de couleurs sont la."""
        jeux = list(self.vue._terminal.availableColorSchemes())
        self.assertGreater(len(jeux), 5)
        # Le nom exact varie avec le paquet : qtermwidget 2.4.0 livre « BreezeModified ».
        self.assertTrue(any(j.startswith("Breeze") for j in jeux), jeux)
        from spyder_konsole import konsole_view
        self.assertTrue(any(j in jeux for j in konsole_view.SCHEMAS_PREFERES),
                        "aucun jeu de couleurs de repli n'existe : le dock aurait "
                        "l'allure par defaut, pas celle de Konsole")


class TestHabillage(BaseTerminal):
    """Le fond doit etre celui de l'IDE, et le profil Konsole doit etre respecte."""

    FOND = "#19232D"        # SpyderPalette.COLOR_BACKGROUND_1
    TEXTE = "#DFE1E2"       # SpyderPalette.COLOR_TEXT_1

    def test_jeu_de_couleurs_derive_porte_le_fond_de_spyder(self):
        """Le fichier fabrique doit contenir le fond de Spyder, en composantes RVB."""
        from spyder_konsole import konsole_view
        nom = konsole_view.schema_aux_couleurs_de_spyder(
            "BreezeModified", self.FOND, self.TEXTE)
        self.assertEqual(nom, "SpyderFond")
        chemin = os.path.join(konsole_view.DOSSIER_SCHEMAS, nom + ".colorscheme")
        contenu = open(chemin, encoding="utf-8").read()
        # #19232D == 25,35,45
        self.assertIn("25,35,45", contenu)
        # Les seize couleurs ANSI de la base doivent avoir survecu : c'est elles qui
        # donnent son allure a la sortie colorisee.
        self.assertIn("[Color1]", contenu)
        self.assertIn("[Color7]", contenu)   # les schemas Konsole vont de Color0 a Color7

    def test_le_terminal_utilise_effectivement_ce_jeu(self):
        from spyder_konsole.konsole_view import VueKonsole
        vue = VueKonsole(couleur_fond=self.FOND, couleur_texte=self.TEXTE)
        try:
            self.assertEqual(vue._schema, "SpyderFond")
        finally:
            vue.deleteLater()

    def test_le_jeu_derive_est_visible_dans_un_processus_neuf(self):
        """Verification dans un processus SEPARE, et c'est indispensable.

        qtermwidget met la liste de ses jeux de couleurs en cache des la premiere
        lecture : dans CE processus, les tests precedents l'ont deja figee, et
        l'assertion serait fausse pour une raison qui n'a rien a voir avec le code
        teste. Un interprete neuf reproduit l'ordre reel — preparation, puis lecture.
        """
        import subprocess
        code = (
            "import sys\n"
            "from PySide6.QtWidgets import QApplication\n"
            "app = QApplication(sys.argv)\n"
            "sys.path.insert(0, %r)\n"
            "from spyder_konsole.konsole_view import preparer_schema, profil_konsole\n"
            "nom = preparer_schema(profil_konsole(), %r, %r)\n"
            "import qtermwidget\n"
            "print(nom in list(qtermwidget.QTermWidget.availableColorSchemes()))\n"
        ) % (os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
             self.FOND, self.TEXTE)
        sortie = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, env=dict(os.environ,
                                                    QT_QPA_PLATFORM="offscreen"))
        self.assertIn("True", sortie.stdout,
                      "le jeu derive n'est pas visible : %s %s"
                      % (sortie.stdout, sortie.stderr[-400:]))

    def test_profil_konsole_lu(self):
        """Le profil de l'utilisateur fait foi pour le shell et l'historique."""
        from spyder_konsole.konsole_view import profil_konsole
        profil = profil_konsole()
        if not profil:
            self.skipTest("aucun profil Konsole sur cette machine")
        self.assertIn("profil", profil)
        # Sur cette machine : Command=/bin/zsh et HistoryMode=2 (illimite).
        if "commande" in profil:
            self.assertTrue(os.path.exists(profil["commande"][0]), profil["commande"])
        if "historique" in profil:
            self.assertIn(profil["historique"], (-1, 0) if profil["historique"] <= 0
                          else (profil["historique"],))

    def test_le_shell_du_profil_est_utilise_par_defaut(self):
        from spyder_konsole.konsole_view import VueKonsole, profil_konsole
        profil = profil_konsole()
        if "commande" not in profil:
            self.skipTest("le profil Konsole ne fixe pas de commande")
        vue = VueKonsole()
        try:
            vue.demarrer()          # sans commande explicite
            self.assertTrue(attendre(lambda: vue._terminal.getShellPID() > 0))
            lien = os.readlink("/proc/%d/exe" % vue._terminal.getShellPID())
            self.assertEqual(os.path.realpath(lien),
                             os.path.realpath(profil["commande"][0]))
        finally:
            vue.arreter(force=True)
            vue.deleteLater()


class TestRaccourcis(BaseTerminal):
    """Ctrl+Maj+C / Ctrl+Maj+V, signales non fonctionnels par l'utilisateur le 26/07.

    On injecte de VRAIES frappes avec QTest : sous Wayland aucun outil externe ne sait
    le faire (kdotool ne pilote que les fenetres), mais QTest envoie l'evenement dans la
    file de Qt, c'est-a-dire exactement ce que produit le clavier. Le test echoue donc
    si les raccourcis ne sont pas poses.
    """

    def setUp(self):
        from spyder_konsole.konsole_view import VueKonsole
        self.vue = VueKonsole(couleur_fond="#19232D", couleur_texte="#DFE1E2")
        self.vue.resize(600, 300)
        self.vue.show()

    def tearDown(self):
        self.vue.arreter(force=True)
        self.vue.deleteLater()
        APPLICATION.processEvents()

    def test_ctrl_maj_c_copie_la_selection(self):
        from qtpy.QtCore import Qt
        from qtpy.QtGui import QGuiApplication
        from qtpy.QtTest import QTest

        self.vue.demarrer(commande=["/bin/sh", "-c", "echo COPIE_PAR_RACCOURCI; sleep 8"])
        self.assertTrue(attendre(
            lambda: "COPIE_PAR_RACCOURCI" in self.contenu()))
        QGuiApplication.clipboard().setText("")
        QTest.keyClick(self.vue, Qt.Key_C, Qt.ControlModifier | Qt.ShiftModifier)
        APPLICATION.processEvents()
        self.assertIn("COPIE_PAR_RACCOURCI", QGuiApplication.clipboard().text())

    def test_ctrl_maj_v_colle_dans_le_terminal(self):
        from qtpy.QtCore import Qt
        from qtpy.QtGui import QGuiApplication
        from qtpy.QtTest import QTest

        self.vue.demarrer(commande=["/bin/sh", "-c", "sleep 8"])
        self.assertTrue(attendre(lambda: self.vue._terminal.getShellPID() > 0))
        QGuiApplication.clipboard().setText("COLLE_PAR_RACCOURCI")
        QTest.keyClick(self.vue, Qt.Key_V, Qt.ControlModifier | Qt.ShiftModifier)
        self.assertTrue(attendre(
            lambda: "COLLE_PAR_RACCOURCI" in self.contenu()))


class TestCtrlCSimple(BaseTerminal):
    """Ctrl+C copie s'il y a une selection, INTERROMPT sinon (demande du 26/07/2026).

    Le piege de cette fonction n'est pas la copie, c'est l'interruption : un terminal
    ou Ctrl+C ne coupe plus rien est inutilisable, et le defaut ne se voit qu'au
    deuxieme appui. Ces tests couvrent donc les trois etats dans l'ordre.
    """

    def setUp(self):
        # Ces tests-la parlent a un shell DEJA lance : ils appuient sur Ctrl+C pendant
        # qu'une commande tourne. Le montage de base ne demarre rien, chaque autre test
        # choisissant sa propre commande.
        super().setUp()
        self.vue.demarrer(commande=["/bin/sh"])
        self.attendre_le_shell()

    def _ctrl_c(self):
        from qtpy.QtCore import Qt
        from qtpy.QtTest import QTest
        QTest.keyClick(self.vue, Qt.Key_C, Qt.ControlModifier)

    def _tout_selectionner(self):
        terminal = self.vue._terminal
        terminal.setSelectionStart(0, 0)
        terminal.setSelectionEnd(terminal.screenLinesCount() - 1,
                                 terminal.screenColumnsCount() - 1)
        return terminal

    def test_sans_selection_ctrl_c_interrompt(self):
        """Le test qui compte : sans lui, on livrerait un terminal qu'on ne peut pas
        interrompre."""
        terminal = self.vue._terminal
        self.vue.envoyer("sleep 60\n")
        self.assertTrue(attendre(
            lambda: terminal.getForegroundProcessId() != terminal.getShellPID()))
        au_travail = terminal.getForegroundProcessId()
        self._ctrl_c()
        self.assertTrue(
            attendre(lambda: terminal.getForegroundProcessId() != au_travail),
            "Ctrl+C n'a pas interrompu la commande en cours")

    def test_avec_selection_ctrl_c_copie_puis_vide_la_selection(self):
        from qtpy.QtGui import QGuiApplication
        terminal = self.vue._terminal
        self.vue.envoyer("echo MARQUEUR_CTRL_C_SIMPLE\n")
        self.assertTrue(attendre(
            lambda: "MARQUEUR_CTRL_C_SIMPLE" in self.contenu()))
        QGuiApplication.clipboard().setText("")
        self._ctrl_c()
        APPLICATION.processEvents()
        self.assertIn("MARQUEUR_CTRL_C_SIMPLE", QGuiApplication.clipboard().text())
        # La selection doit etre VIDE ensuite, sinon le Ctrl+C suivant copierait encore.
        # `setSelectionEnd(0, 0)` laissait un caractere : mesure du 26/07/2026.
        self.assertEqual(terminal.selectedText(False), "")

    def test_ctrl_c_redevient_une_interruption_juste_apres_une_copie(self):
        from qtpy.QtGui import QGuiApplication
        terminal = self.vue._terminal
        self.vue.envoyer("echo A_COPIER; sleep 60\n")
        self.assertTrue(attendre(
            lambda: "A_COPIER" in self.contenu()))
        QGuiApplication.clipboard().setText("")
        self._ctrl_c()                      # copie
        APPLICATION.processEvents()
        au_travail = terminal.getForegroundProcessId()
        self._ctrl_c()                      # doit interrompre
        self.assertTrue(
            attendre(lambda: terminal.getForegroundProcessId() != au_travail),
            "le second Ctrl+C a encore copie au lieu d'interrompre")

    def test_ctrl_v_simple_colle(self):
        from qtpy.QtCore import Qt
        from qtpy.QtGui import QGuiApplication
        from qtpy.QtTest import QTest
        QGuiApplication.clipboard().setText("COLLE_CTRL_V_SIMPLE")
        QTest.keyClick(self.vue, Qt.Key_V, Qt.ControlModifier)
        self.assertTrue(attendre(
            lambda: "COLLE_CTRL_V_SIMPLE" in self.contenu()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
