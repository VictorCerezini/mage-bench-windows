package mage.client.util;

import com.google.gson.Gson;
import mage.client.MageFrame;
import mage.client.SessionHandler;

import javax.swing.JOptionPane;
import javax.swing.Timer;
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Local subscription player integration. Authentication stays with the Codex CLI. */
public final class SubscriptionSupport {
    public static final String PLAYER_TYPE = "ChatGPT subscription";
    private static final Gson JSON = new Gson();
    private static Catalog catalog;
    private static final Map<UUID, Path> activePlayers = new ConcurrentHashMap<>();

    private SubscriptionSupport() {
    }

    public static final class Model {
        public String id;
        public String name;
        public List<String> efforts;
        public String defaultEffort;
        public boolean isDefault;

        @Override
        public String toString() {
            return name;
        }
    }

    private static final class Catalog {
        String provider;
        List<Model> models;
    }

    public static boolean isConfigured() {
        return System.getProperty("xmage.subscription.catalog") != null;
    }

    public static synchronized List<Model> models() {
        if (catalog == null) {
            try (Reader reader = Files.newBufferedReader(Path.of(requiredProperty("catalog")), StandardCharsets.UTF_8)) {
                catalog = JSON.fromJson(reader, Catalog.class);
                if (!"chatgpt_subscription".equals(catalog.provider) || catalog.models.isEmpty()) {
                    throw new IllegalStateException("The ChatGPT model catalog is empty or invalid");
                }
            } catch (IOException error) {
                throw new IllegalStateException("Could not read the ChatGPT model catalog", error);
            }
        }
        return catalog.models;
    }

    private static String requiredProperty(String name) {
        String value = System.getProperty("xmage.subscription." + name);
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException("Open this client with windows/Play-vs-ChatGPT.cmd first");
        }
        return value;
    }

    public static void validate(String deck, Model model, String effort) {
        if (!isConfigured() || !"127.0.0.1".equals(SessionHandler.getSession().getServerHost())) {
            throw new IllegalArgumentException("ChatGPT subscription play requires the isolated local Windows launcher");
        }
        if (deck.isEmpty() || !Files.isRegularFile(Path.of(deck))) {
            throw new IllegalArgumentException("Select a deck file for the ChatGPT opponent");
        }
        if (model == null || !models().contains(model) || !model.efforts.contains(effort)) {
            throw new IllegalArgumentException("Select an available ChatGPT model and supported reasoning level");
        }
    }

    public static void start(UUID tableId, int seat, String deck, Model model, String effort) throws IOException {
        validate(deck, model, effort);
        Path run = Path.of(requiredProperty("runs")).resolve(tableId + "-seat-" + seat);
        Files.createDirectories(run);
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("table_id", tableId.toString());
        request.put("server_port", Integer.parseInt(requiredProperty("serverPort")));
        request.put("deck", Path.of(deck).toAbsolutePath().toString());
        request.put("model", model.id);
        request.put("reasoning", effort);
        request.put("username", "ChatGPT " + seat);
        request.put("owner_pid", ProcessHandle.current().pid());
        request.put("run", run.toString());
        request.put("catalog", requiredProperty("catalog"));
        ProcessBuilder builder = new ProcessBuilder(requiredProperty("python"), "-u", "-m", "windows.gui_player");
        builder.directory(Path.of(requiredProperty("repo")).toFile());
        builder.redirectErrorStream(true);
        builder.redirectOutput(run.resolve("supervisor.log").toFile());
        Process process = builder.start();
        activePlayers.put(tableId, run);
        try (var input = process.getOutputStream()) {
            input.write(JSON.toJson(request).getBytes(StandardCharsets.UTF_8));
        }
        Timer monitor = new Timer(1000, null);
        monitor.addActionListener(event -> {
            if (!process.isAlive()) {
                monitor.stop();
                activePlayers.remove(tableId);
                if (process.exitValue() != 0) {
                    JOptionPane.showMessageDialog(MageFrame.getDesktop(),
                            "The ChatGPT player stopped. Close this table before trying again.\n"
                                    + "Details: " + run.resolve("supervisor.log"),
                            "ChatGPT player", JOptionPane.ERROR_MESSAGE);
                }
            }
        });
        monitor.start();
    }

    public static void stop(UUID tableId) {
        Path run = activePlayers.get(tableId);
        if (run != null) {
            try {
                Files.writeString(run.resolve("cancel.requested"), "Table closed", StandardCharsets.UTF_8);
            } catch (IOException error) {
                throw new IllegalStateException("Could not stop the ChatGPT player for this table", error);
            }
        }
    }
}
