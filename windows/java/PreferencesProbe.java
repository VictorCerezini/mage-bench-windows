import java.util.prefs.Preferences;

class PreferencesProbe {
    public static void main(String[] args) {
        String value = Preferences.userRoot().node("/mage/client").get("gameLogJsonAutoSave", "missing");
        if (!"false".equals(value)) throw new AssertionError(value);
        System.out.println("PASS: isolated client preference disables redundant raw callback log");
    }
}
