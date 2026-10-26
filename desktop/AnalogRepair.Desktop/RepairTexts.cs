namespace AnalogRepair.Desktop;

/// <summary>
/// Texts of the Repair page that the code builds or changes at run time, kept in
/// one place for a later translation. Built-in preset names and descriptions live
/// with the presets in <see cref="RepairPreset.BuiltIn"/>.
/// </summary>
internal static class RepairTexts
{
    // Preset state above the cards.
    public const string CustomSettings = "Custom settings";
    public const string CustomBasedOn = "Custom · based on {0}";
    public const string UserPresetLine = "Your preset · {0}";
    public const string UserPresetTip = "Your own preset. Right-click or use … to rename, update or delete it.";
    public const string MoreFor = "Options for {0}";

    // Saving, renaming and deleting.
    public const string SaveTitle = "NAME FOR THE CURRENT SETTINGS";
    public const string RenameTitle = "NEW NAME FOR \"{0}\"";
    public const string Save = "Save";
    public const string Rename = "Rename";
    public const string RenameMenu = "Rename…";
    public const string UpdateMenu = "Update with current settings";
    public const string DeleteMenu = "Delete…";
    public const string NameMissing = "Type a name first.";
    public const string NameBuiltIn = "A built-in preset has that name. Choose another one.";
    public const string NameTaken = "You already have a preset with that name. Choose another one, or use Update on that preset.";
    public const string Saved = "Saved \"{0}\".";
    public const string Renamed = "Renamed to \"{0}\".";
    public const string Updated = "\"{0}\" now holds the current settings.";
    public const string Deleted = "Deleted \"{0}\".";
    public const string DeleteQuestion = "Delete your preset \"{0}\"?";

    // Advanced fold.
    public const string AdvancedShow = "Show ▾";
    public const string AdvancedHide = "Hide ▴";
    public const string AdvancedShowTip = "Show every repair on its own slider";
    public const string AdvancedHideTip = "Fold the sliders away again";

    // Source notes.
    public const string TapeNote = "Tape (VHS, Hi8, camcorder): tracking noise, the torn bottom band, wobbling lines and smeared colour. 0 turns a repair off.";
    public const string FilmNote = "Film (8 mm, Super 8, 16 mm): dust, scratches, flicker and gate weave. 0 turns a repair off.";

    // Speed notes.
    public const string FastNote = "Quickest; fine for a first look.";
    public const string BalancedNote = "Recommended: nearly Best, in far less time.";
    public const string BestNote = "Finest result; takes the longest.";

    // The summary line: "Tape repair: tape noise strong, noise medium, …".
    public const string SummaryTape = "Tape repair";
    public const string SummaryFilm = "Film repair";
    public const string SummaryNothing = "Nothing is repaired; the picture is only re-encoded.";
    public const string Light = "light";
    public const string Medium = "medium";
    public const string Strong = "strong";
    public const string TapeNoise = "tape noise";
    public const string Noise = "noise";
    public const string Colour = "colour";
    public const string Dust = "dust";
    public const string Flicker = "flicker";
    public const string Shake = "shake";
    public const string KeepsGrain = "keeps the grain";
    public const string RemovesStamp = "removes the date stamp";
    public const string Upscaled = "upscaled {0}";
    public const string WithLook = "with a look";
}
