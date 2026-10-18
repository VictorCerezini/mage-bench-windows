package experiment;

import java.util.HashMap;
import java.util.Map;
import java.util.prefs.AbstractPreferences;
import java.util.prefs.BackingStoreException;
import java.util.prefs.Preferences;
import java.util.prefs.PreferencesFactory;

/** Process-local Java preferences for the isolated XMage experiment. */
public final class IsolatedPreferencesFactory implements PreferencesFactory {
    private final Preferences userRoot = new MemoryPreferences(null, "");
    private final Preferences systemRoot = new MemoryPreferences(null, "");

    public IsolatedPreferencesFactory() {
        // Keep Mage-Bench's event logs; omit XMage's separate raw callback dump.
        userRoot.node("/mage/client").put("gameLogJsonAutoSave", "false");
    }

    @Override
    public Preferences userRoot() {
        return userRoot;
    }

    @Override
    public Preferences systemRoot() {
        return systemRoot;
    }

    private static final class MemoryPreferences extends AbstractPreferences {
        private final Map<String, String> values = new HashMap<>();
        private final Map<String, MemoryPreferences> children = new HashMap<>();

        MemoryPreferences(AbstractPreferences parent, String name) {
            super(parent, name);
            newNode = parent != null;
        }

        @Override
        protected void putSpi(String key, String value) {
            values.put(key, value);
        }

        @Override
        protected String getSpi(String key) {
            return values.get(key);
        }

        @Override
        protected void removeSpi(String key) {
            values.remove(key);
        }

        @Override
        protected void removeNodeSpi() throws BackingStoreException {
            MemoryPreferences parentNode = (MemoryPreferences) parent();
            if (parentNode != null) {
                synchronized (parentNode.lock) {
                    parentNode.children.remove(name());
                }
            }
            values.clear();
            children.clear();
        }

        @Override
        protected String[] keysSpi() {
            return values.keySet().toArray(String[]::new);
        }

        @Override
        protected String[] childrenNamesSpi() {
            return children.keySet().toArray(String[]::new);
        }

        @Override
        protected AbstractPreferences childSpi(String name) {
            return children.computeIfAbsent(name, key -> new MemoryPreferences(this, key));
        }

        @Override
        protected void syncSpi() {
            // This store intentionally has no external backing state.
        }

        @Override
        protected void flushSpi() {
            // Process-local preferences are discarded when the JVM exits.
        }
    }
}
