package experiment;

import javax.swing.JLayeredPane;
import javax.swing.SwingUtilities;
import mage.cards.repository.CardScanner;
import mage.client.MageFrame;
import mage.client.SessionHandler;
import mage.client.dialog.NewTableDialog;
import mage.client.dialog.PreferencesDialog;

/** Opens the regular match configuration on an isolated local server. */
public final class MatchGui {
    public static void main(String[] args) {
        CardScanner.scanned = true;
        MageFrame.main(new String[]{"-lite"});
        Thread opener = new Thread(() -> {
            try {
                long deadline = System.currentTimeMillis() + 180_000;
                while ((SessionHandler.getSession() == null || !SessionHandler.isConnected())
                        && System.currentTimeMillis() < deadline) {
                    Thread.sleep(500);
                }
                if (!SessionHandler.isConnected()) {
                    throw new IllegalStateException("Match GUI did not connect to the isolated server");
                }
                SwingUtilities.invokeLater(() -> {
                    PreferencesDialog.saveValue(PreferencesDialog.KEY_NEW_TABLE_NAME, "You vs LLM");
                    PreferencesDialog.saveValue(PreferencesDialog.KEY_NEW_TABLE_NUMBER_OF_WINS, "1");
                    PreferencesDialog.saveValue(PreferencesDialog.KEY_NEW_TABLE_TIME_LIMIT, "0");
                    PreferencesDialog.saveValue(PreferencesDialog.KEY_NEW_TABLE_DECK_TYPE, "Limited");
                    PreferencesDialog.saveValue(PreferencesDialog.KEY_NEW_TABLE_DECK_FILE, System.getProperty("experiment.deck"));
                    PreferencesDialog.saveValue(PreferencesDialog.KEY_NEW_TABLE_PLAYER_DECKS, System.getProperty("experiment.deck"));
                    PreferencesDialog.saveValue("chatgptSeat2", "true");
                    MageFrame.getInstance().setTitle("XMage - LLM subscription matches");
                    NewTableDialog dialog = new NewTableDialog();
                    MageFrame.getDesktop().add(dialog, JLayeredPane.MODAL_LAYER);
                    System.out.println("MATCH_GUI_READY");
                    dialog.showDialog(SessionHandler.getSession().getMainRoomId());
                });
            } catch (Exception error) {
                error.printStackTrace();
                System.exit(1);
            }
        }, "Match-GUI-Open");
        opener.setDaemon(true);
        opener.start();
    }
}
