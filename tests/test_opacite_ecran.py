"""L'ecran du terminal reste opaque sous la feuille de style de l'application.

Sous qdarkstyle (feuille d'application de Spyder), chaque polissage retire
WA_OpaquePaintEvent au Konsole::TerminalDisplay de qtermwidget : chacune de ses repeintes
refaisait alors les parents dessous, jusqu'a la fenetre entiere (Claude Dock en mosaique,
12/11/2026 : 8 Mpx/s, le clavier qui rame). VueKonsole pose une garde.

`test_amont_retire_toujours_l_opacite` dit si la rustine est encore necessaire : le jour
ou il echoue, Qt ou qtermwidget ne retirent plus l'attribut, et la garde peut partir.
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qtpy.QtCore import Qt  # noqa: E402
from qtpy.QtGui import QColor  # noqa: E402
from qtpy.QtWidgets import QApplication, QWidget  # noqa: E402

try:
    import qdarkstyle
    import qtermwidget  # noqa: F401
except ImportError:  # pragma: no cover - environnement sans la pile de Spyder
    qdarkstyle = None

from spyder_konsole.konsole_view import VueKonsole  # noqa: E402

APP = QApplication.instance() or QApplication(sys.argv)


@unittest.skipIf(qdarkstyle is None, "qdarkstyle ou qtermwidget absent")
class OpaciteEcran(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._feuille = APP.styleSheet()
        APP.setStyleSheet(qdarkstyle.load_stylesheet(qt_api=os.environ.get("QT_API", "pyside6")))

    @classmethod
    def tearDownClass(cls):
        APP.setStyleSheet(cls._feuille)

    def _vue(self):
        vue = VueKonsole()
        vue.resize(600, 400)       # un ecran de largeur nulle ne recoit aucune repeinte
        vue.show()
        APP.processEvents()
        self.addCleanup(vue.deleteLater)
        return vue

    def test_amont_retire_toujours_l_opacite(self):
        vue = self._vue()
        ecran = vue._ecran_terminal
        ecran.removeEventFilter(vue)   # sans la garde
        ecran.style().unpolish(ecran)
        ecran.style().polish(ecran)
        self.assertFalse(ecran.testAttribute(Qt.WA_OpaquePaintEvent))

    def test_ecran_opaque_apres_changements_de_fond(self):
        vue = self._vue()
        ecran = vue._ecran_terminal
        self.assertEqual(ecran.metaObject().className(), "Konsole::TerminalDisplay")
        # Couleur nouvelle (setStyleSheet), puis deja connue (polissage direct, sans evenement).
        for couleur in ("#200000", "#002000", "#200000"):
            vue._poser_fond(QColor(couleur))
            vue.grab()                 # une repeinte : la garde rattrape le polissage direct
            self.assertTrue(ecran.testAttribute(Qt.WA_OpaquePaintEvent), couleur)

    def test_rendu_identique(self):
        vue = self._vue()
        ecran = vue._ecran_terminal
        vue._poser_fond(QColor("#200000"))
        ecran.removeEventFilter(vue)
        ecran.setAttribute(Qt.WA_OpaquePaintEvent, False)
        sans = vue.grab().toImage()
        ecran.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.assertEqual(sans, vue.grab().toImage())


if __name__ == "__main__":
    unittest.main()
