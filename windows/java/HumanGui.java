package experiment;

import java.util.UUID;
import javax.swing.SwingUtilities;
import mage.cards.decks.DeckCardLists;
import mage.cards.decks.importer.DeckImporter;
import mage.cards.repository.CardScanner;
import mage.client.MageFrame;
import mage.client.SessionHandler;
import mage.constants.TableState;
import mage.players.PlayerType;
import mage.remote.Session;
import mage.view.TableView;

/** Opens the unmodified player client and joins only its own local human seat. */
public final class HumanGui {
    public static void main(String[] args) {
        CardScanner.scanned = true;
        MageFrame.main(new String[]{"-lite"});
        Thread joiner = new Thread(() -> {
            try {
                long deadline = System.currentTimeMillis() + 180_000;
                while (!connected() && System.currentTimeMillis() < deadline) {
                    Thread.sleep(500);
                }
                if (!connected()) {
                    throw new IllegalStateException("Human GUI did not connect to the isolated server");
                }
                Session session = SessionHandler.getSession();
                UUID roomId = session.getMainRoomId();
                UUID wanted = UUID.fromString(System.getProperty("experiment.tableId"));
                DeckCardLists deck = DeckImporter.importDeckFromFile(System.getProperty("experiment.deck"), false);
                if (deck.getCards().size() < 40) {
                    throw new IllegalArgumentException("The human deck imported fewer than 40 cards");
                }
                while (System.currentTimeMillis() < deadline) {
                    for (TableView table : session.getTables(roomId)) {
                        if (wanted.equals(table.getTableId()) && table.getTableState() == TableState.WAITING) {
                            if (!SessionHandler.joinTable(roomId, wanted, "You", PlayerType.HUMAN, 1, deck, "")) {
                                throw new IllegalStateException("Could not join the human seat");
                            }
                            SwingUtilities.invokeLater(() -> MageFrame.getInstance().setTitle("XMage - You vs ChatGPT"));
                            System.out.println("HUMAN_GUI_JOINED table=" + wanted + " cards=" + deck.getCards().size());
                            return;
                        }
                    }
                    Thread.sleep(500);
                }
                throw new IllegalStateException("The human table did not become available");
            } catch (Exception error) {
                error.printStackTrace();
                System.exit(1);
            }
        }, "Human-GUI-Join");
        joiner.setDaemon(true);
        joiner.start();
    }

    private static boolean connected() {
        return SessionHandler.getSession() != null && SessionHandler.isConnected();
    }
}
