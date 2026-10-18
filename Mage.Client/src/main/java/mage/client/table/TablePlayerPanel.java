package mage.client.table;

import mage.cards.decks.importer.DeckImporter;
import mage.client.SessionHandler;
import mage.client.util.ClientDefaultSettings;
import mage.client.util.Event;
import mage.client.util.Listener;
import mage.client.util.SubscriptionSupport;
import mage.client.dialog.PreferencesDialog;
import mage.players.PlayerType;
import mage.game.match.MatchOptions;

import javax.swing.*;
import java.io.IOException;
import java.awt.BorderLayout;
import java.awt.FlowLayout;
import java.util.UUID;

/**
 * @author BetaSteward_at_googlemail.com
 */
public class TablePlayerPanel extends javax.swing.JPanel {

    protected final PlayerTypeEventSource playerTypeEventSource = new PlayerTypeEventSource();
    private final JPanel subscriptionPanel = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 0));
    private final JComboBox<SubscriptionSupport.Model> modelChoice = new JComboBox<>();
    private final JComboBox<String> reasoningChoice = new JComboBox<>();
    private int playerNumber;

    public TablePlayerPanel() {
        initComponents();
        // Keep subscription controls outside the form editor's generated layout.
        JPanel playerRow = new JPanel(new BorderLayout(8, 0));
        JPanel typeColumn = new JPanel(new java.awt.GridLayout(2, 1, 0, 3));
        JPanel typeRow = new JPanel(new FlowLayout(FlowLayout.LEFT, 4, 0));
        typeRow.add(lbPlayerType);
        typeRow.add(cbPlayerType);
        typeColumn.add(lblPlayerNum);
        typeColumn.add(typeRow);
        playerRow.add(typeColumn, BorderLayout.WEST);
        playerRow.add(newPlayerPanel, BorderLayout.CENTER);
        removeAll();
        setLayout(new BorderLayout(0, 6));
        add(playerRow, BorderLayout.CENTER);
        subscriptionPanel.add(new JLabel("Model:"));
        modelChoice.setPrototypeDisplayValue(null);
        modelChoice.setToolTipText("Models available through your signed-in subscription");
        modelChoice.getAccessibleContext().setAccessibleName("Subscription model");
        reasoningChoice.getAccessibleContext().setAccessibleName("Subscription reasoning level");
        subscriptionPanel.add(modelChoice);
        subscriptionPanel.add(new JLabel("Reasoning:"));
        subscriptionPanel.add(reasoningChoice);
        subscriptionPanel.add(new JLabel("Subscription usage begins when the match starts."));
        add(subscriptionPanel, BorderLayout.SOUTH);
        subscriptionPanel.setVisible(false);
        modelChoice.addActionListener(event -> updateReasoning());
        this.newPlayerPanel.setVisible(false);
    }

    public void init(int playerNum, PlayerType playerType, int playerSkill, String playerDeck) {
        playerNumber = playerNum;
        cbPlayerType.setModel(new DefaultComboBoxModel(SessionHandler.getPlayerTypes()));
        if (SubscriptionSupport.isConfigured()) {
            for (SubscriptionSupport.Provider provider : SubscriptionSupport.providers()) {
                cbPlayerType.addItem(provider);
            }
        }
        this.lblPlayerNum.setText("Player " + playerNum);
        if (ClientDefaultSettings.otherPlayerIndex != null) {
            Integer index = Integer.parseInt(ClientDefaultSettings.otherPlayerIndex);
            if (index >= cbPlayerType.getItemCount()) {
                cbPlayerType.setSelectedIndex(cbPlayerType.getItemCount() - 1);
            } else {
                cbPlayerType.setSelectedIndex(index);
            }
        }
        if (playerType != null) {
            this.cbPlayerType.setSelectedItem(playerType);
        }
        this.newPlayerPanel.setDeckFile(playerDeck);
        this.newPlayerPanel.setSkillLevel(playerSkill);
    }

    public static String extractAiPlayerNumberFromLabel(String label) {
        return ClientDefaultSettings.computerName + " " + label.substring(Math.max(0, label.length() - 2)).trim();
    }

    public boolean joinTable(UUID roomId, UUID tableId) throws IOException, ClassNotFoundException {
        if (isSubscriptionPlayer()) {
            throw new IllegalStateException("Start subscription players after the table owner has joined");
        }
        if (this.cbPlayerType.getSelectedItem() != PlayerType.HUMAN) {
            return SessionHandler.joinTable(roomId, tableId, this.newPlayerPanel.getPlayerName(), (PlayerType) this.cbPlayerType.getSelectedItem(), this.newPlayerPanel.getSkillLevel(), DeckImporter.importDeckFromFile(this.newPlayerPanel.getDeckFile(), true), "");
        }
        return true;
    }

    public PlayerType getPlayerType() {
        if (isSubscriptionPlayer()) {
            return PlayerType.HUMAN;
        }
        return PlayerType.getByDescription(this.cbPlayerType.getSelectedItem().toString());
    }

    public boolean isSubscriptionPlayer() {
        return getProvider() != null;
    }

    private SubscriptionSupport.Provider getProvider() {
        return SubscriptionSupport.provider(cbPlayerType.getSelectedItem());
    }

    public void startSubscription(UUID tableId, MatchOptions options) throws IOException {
        SubscriptionSupport.start(getProvider(), tableId, playerNumber, getPlayerDeck(), getModel(), getReasoning(), options);
    }

    /** Fill the model list from the selected provider, keeping the selection when the provider is unchanged. */
    private void updateModels() {
        SubscriptionSupport.Provider provider = getProvider();
        if (provider == null || provider.models.contains(modelChoice.getSelectedItem())) {
            return;
        }
        modelChoice.removeAllItems();
        for (SubscriptionSupport.Model model : provider.models) {
            modelChoice.addItem(model);
        }
        for (SubscriptionSupport.Model model : provider.models) {
            if (model.isDefault) {
                modelChoice.setSelectedItem(model);
            }
        }
    }

    private SubscriptionSupport.Model getModel() {
        return (SubscriptionSupport.Model) modelChoice.getSelectedItem();
    }

    private String getReasoning() {
        return (String) reasoningChoice.getSelectedItem();
    }

    private void updateReasoning() {
        SubscriptionSupport.Model model = getModel();
        if (model != null) {
            reasoningChoice.setModel(new DefaultComboBoxModel<>(model.efforts.toArray(new String[0])));
            reasoningChoice.setSelectedItem(model.defaultEffort);
        }
    }

    public void validateSubscription() {
        SubscriptionSupport.validate(getProvider(), getPlayerDeck(), getModel(), getReasoning());
    }

    public void saveSubscriptionSettings(String version) {
        String key = "chatgptSeat" + playerNumber + version;
        PreferencesDialog.saveValue(key, Boolean.toString(isSubscriptionPlayer()));
        if (isSubscriptionPlayer()) {
            PreferencesDialog.saveValue(key + "Provider", getProvider().id);
            PreferencesDialog.saveValue(key + "Model", getModel().id);
            PreferencesDialog.saveValue(key + "Reasoning", getReasoning());
        }
    }

    public void loadSubscriptionSettings(String version) {
        String key = "chatgptSeat" + playerNumber + version;
        if (SubscriptionSupport.isConfigured() && Boolean.parseBoolean(PreferencesDialog.getCachedValue(key, "false"))) {
            // Settings saved before Claude support have no provider; a provider that is not signed in falls back to the first available.
            SubscriptionSupport.Provider provider = SubscriptionSupport.providerById(
                    PreferencesDialog.getCachedValue(key + "Provider", "chatgpt_subscription"));
            boolean savedProvider = provider != null;
            if (!savedProvider) {
                provider = SubscriptionSupport.providers().get(0);
            }
            cbPlayerType.setSelectedItem(provider);
            // Free model lists rotate, so a saved model or level that is gone keeps the provider's defaults.
            String selected = savedProvider ? PreferencesDialog.getCachedValue(key + "Model", "") : "";
            provider.models.stream().filter(item -> item.id.equals(selected)).findFirst().ifPresent(model -> {
                modelChoice.setSelectedItem(model);
                String effort = PreferencesDialog.getCachedValue(key + "Reasoning", model.defaultEffort);
                if (model.efforts.contains(effort)) {
                    reasoningChoice.setSelectedItem(effort);
                }
            });
        }
    }

    public int getPlayerSkill() {
        return newPlayerPanel.getSkillLevel();
    }

    public String getPlayerDeck() {
        return newPlayerPanel.getDeckFile();
    }

    public void addPlayerTypeEventListener(Listener<Event> listener) {
        playerTypeEventSource.addListener(listener);
    }

    public void clearPlayerTypeEventListeners() {
        playerTypeEventSource.clearListeners();
    }


    /**
     * This method is called from within the constructor to
     * initialize the form.
     * WARNING: Do NOT modify this code. The content of this method is
     * always regenerated by the Form Editor.
     */
    @SuppressWarnings("unchecked")
    // <editor-fold defaultstate="collapsed" desc="Generated Code">//GEN-BEGIN:initComponents
    private void initComponents() {

        lbPlayerType = new javax.swing.JLabel();
        cbPlayerType = new javax.swing.JComboBox();
        newPlayerPanel = new mage.client.table.NewPlayerPanel();
        lblPlayerNum = new javax.swing.JLabel();

        lbPlayerType.setText("Type:");

        cbPlayerType.addActionListener(evt -> cbPlayerTypeActionPerformed(evt));

        lblPlayerNum.setFont(new java.awt.Font("Tahoma", 1, 11));
        lblPlayerNum.setText("Player #");

        javax.swing.GroupLayout layout = new javax.swing.GroupLayout(this);
        this.setLayout(layout);
        layout.setHorizontalGroup(
                layout.createParallelGroup(javax.swing.GroupLayout.Alignment.LEADING)
                        .addGroup(layout.createSequentialGroup()
                                .addContainerGap()
                                .addGroup(layout.createParallelGroup(javax.swing.GroupLayout.Alignment.LEADING)
                                        .addComponent(lblPlayerNum)
                                        .addGroup(layout.createSequentialGroup()
                                                .addComponent(lbPlayerType)
                                                .addPreferredGap(javax.swing.LayoutStyle.ComponentPlacement.RELATED)
                                                .addComponent(cbPlayerType, javax.swing.GroupLayout.PREFERRED_SIZE, 166, javax.swing.GroupLayout.PREFERRED_SIZE)))
                                .addPreferredGap(javax.swing.LayoutStyle.ComponentPlacement.RELATED)
                                .addComponent(newPlayerPanel, javax.swing.GroupLayout.DEFAULT_SIZE, 318, Short.MAX_VALUE))
        );
        layout.setVerticalGroup(
                layout.createParallelGroup(javax.swing.GroupLayout.Alignment.LEADING)
                        .addGroup(layout.createSequentialGroup()
                                .addGroup(layout.createParallelGroup(javax.swing.GroupLayout.Alignment.LEADING)
                                        .addGroup(layout.createSequentialGroup()
                                                .addComponent(lblPlayerNum)
                                                .addPreferredGap(javax.swing.LayoutStyle.ComponentPlacement.RELATED)
                                                .addGroup(layout.createParallelGroup(javax.swing.GroupLayout.Alignment.BASELINE)
                                                        .addComponent(cbPlayerType, javax.swing.GroupLayout.PREFERRED_SIZE, javax.swing.GroupLayout.DEFAULT_SIZE, javax.swing.GroupLayout.PREFERRED_SIZE)
                                                        .addComponent(lbPlayerType)))
                                        .addComponent(newPlayerPanel, javax.swing.GroupLayout.DEFAULT_SIZE, 43, Short.MAX_VALUE))
                                .addContainerGap())
        );
    }// </editor-fold>//GEN-END:initComponents

    private void cbPlayerTypeActionPerformed(java.awt.event.ActionEvent evt) {//GEN-FIRST:event_cbPlayerTypeActionPerformed
        if (cbPlayerType.getSelectedItem() == null) {
            return;
        }
        updateModels();
        subscriptionPanel.setVisible(isSubscriptionPlayer());
        newPlayerPanel.showLevel(!isSubscriptionPlayer());
        if (isSubscriptionPlayer() || getPlayerType() != PlayerType.HUMAN) {
            this.newPlayerPanel.setVisible(true);
            this.newPlayerPanel.setPlayerName(isSubscriptionPlayer() ? getProvider().playerName + " " + playerNumber
                    : extractAiPlayerNumberFromLabel(this.lblPlayerNum.getText()));
        } else {
            this.newPlayerPanel.setVisible(false);
        }
        this.revalidate();
        this.repaint();
        this.playerTypeEventSource.playerTypeChanged();
    }//GEN-LAST:event_cbPlayerTypeActionPerformed


    // Variables declaration - do not modify//GEN-BEGIN:variables
    private javax.swing.JComboBox cbPlayerType;
    private javax.swing.JLabel lbPlayerType;
    private javax.swing.JLabel lblPlayerNum;
    private mage.client.table.NewPlayerPanel newPlayerPanel;
    // End of variables declaration//GEN-END:variables

}
