using System.Text.Json;
using System.Text.Json.Serialization;

namespace AnalogRepair.Desktop;

/// <summary>Repair settings that can be saved as a preset and restored between runs.</summary>
public sealed class RepairPreset
{
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    // The source: "tape" (VHS, Hi8, camcorder) or "film" (8 mm, Super 8, 16 mm).
    [JsonPropertyName("signal")] public string Signal { get; set; } = "tape";
    [JsonPropertyName("colour")] public int Colour { get; set; } = 40;
    [JsonPropertyName("noise")] public int Noise { get; set; } = 50;
    [JsonPropertyName("detail")] public int Detail { get; set; } = 10;
    [JsonPropertyName("size")] public int Size { get; set; } = 100;
    [JsonPropertyName("osd")] public bool Osd { get; set; }
    [JsonPropertyName("effort")] public string Effort { get; set; } = "balanced";
    [JsonPropertyName("quality")] public int Quality { get; set; } = 18;
    [JsonPropertyName("sizeCapMb")] public int SizeCapMb { get; set; }
    // The finishing look, strengths 0..100; off unless switched on.
    [JsonPropertyName("look")] public bool Look { get; set; }
    [JsonPropertyName("lookGrade")] public int LookGrade { get; set; }
    [JsonPropertyName("lookGlow")] public int LookGlow { get; set; }
    [JsonPropertyName("lookVignette")] public int LookVignette { get; set; }
    [JsonPropertyName("lookGrain")] public int LookGrain { get; set; }
    [JsonPropertyName("lookFringe")] public int LookFringe { get; set; }
    // The repairs of tapes and film, 0..100; the defaults are those of the tape preset.
    [JsonPropertyName("stabilise")] public int Stabilise { get; set; } = 30;
    [JsonPropertyName("flicker")] public int Flicker { get; set; } = 30;
    [JsonPropertyName("dust")] public int Dust { get; set; } = 30;
    [JsonPropertyName("tape")] public int Tape { get; set; } = 60;
    [JsonPropertyName("keepGrain")] public bool KeepGrain { get; set; }

    public RepairPreset Clone() => (RepairPreset)MemberwiseClone();

    /// <summary>One plain line on the preset card; built-in presets only.</summary>
    [JsonIgnore] public string Description { get; init; } = "";
    /// <summary>The longer explanation in the card's tooltip; built-in presets only.</summary>
    [JsonIgnore] public string Tip { get; init; } = "";
    [JsonIgnore] public bool IsBuiltIn => BuiltIn.Contains(this);

    /// <summary>
    /// True when the repair itself is the same: source, every repair slider, size
    /// and speed. The date stamp, the look and the export quality are not compared;
    /// they belong to the footage or are a finish on top, and they stay as they are
    /// when a built-in preset is chosen.
    /// </summary>
    public bool SameRepair(RepairPreset other) =>
        Signal == other.Signal && Colour == other.Colour && Noise == other.Noise && Detail == other.Detail
        && Size == other.Size && Effort == other.Effort && Stabilise == other.Stabilise
        && Flicker == other.Flicker && Dust == other.Dust && Tape == other.Tape && KeepGrain == other.KeepGrain;

    /// <summary>
    /// Presets that ship with the app; they cannot be renamed or deleted. The first
    /// one of each source is what choosing that source by hand starts from. Names,
    /// descriptions and tips are the texts of the cards on the Repair page.
    /// </summary>
    public static IReadOnlyList<RepairPreset> BuiltIn { get; } =
    [
        new() { Name = "VHS tape", Description = "Everyday tape: noise and colour",
                Tip = "VHS or S-VHS in fair shape: calms the noise, pulls smeared colour back onto the edges and repairs tracking noise.",
                Signal = "tape", Colour = 40, Noise = 50, Detail = 10, Stabilise = 30, Flicker = 30, Dust = 30, Tape = 60 },
        new() { Name = "Worn VHS tape", Description = "Heavy tracking noise, dropouts",
                Tip = "Tapes that were played often or stored badly: strong repair of tracking noise and the torn bottom band, dropouts refilled, more colour and noise repair.",
                Signal = "tape", Colour = 60, Noise = 65, Detail = 10, Stabilise = 30, Flicker = 40, Dust = 70, Tape = 90 },
        new() { Name = "Camcorder tape", Description = "Hi8, Video8: steadies the shake",
                Tip = "Hand-held Hi8, Video8 or VHS-C recordings: steadies the shake and calms the noise; tape noise is usually milder than on VHS.",
                Signal = "tape", Colour = 50, Noise = 50, Detail = 15, Stabilise = 55, Flicker = 30, Dust = 30, Tape = 45 },
        new() { Name = "8 mm / Super 8", Description = "Film: dust, flicker, gate weave",
                Tip = "Home movie film: removes dust and scratches, evens out flicker and steadies the gate weave. Keeps a little grain so the film does not look waxy.",
                Signal = "film", Colour = 0, Noise = 30, Detail = 10, Stabilise = 50, Flicker = 60, Dust = 60, Tape = 0, KeepGrain = true },
        new() { Name = "16 mm film", Description = "Finer film, a lighter touch",
                Tip = "16 mm has finer grain and a steadier gate than 8 mm: the same repairs, applied more gently.",
                Signal = "film", Colour = 0, Noise = 20, Detail = 10, Stabilise = 30, Flicker = 40, Dust = 50, Tape = 0, KeepGrain = true },
        new() { Name = "Archive, 2× Best", Description = "VHS repair, upscaled 2× · slow",
                Tip = "The VHS tape repair at the Best speed, upscaled to twice the size with detail from the neighbouring frames. Takes the longest; for the copy you keep.",
                Signal = "tape", Colour = 40, Noise = 50, Detail = 15, Stabilise = 30, Flicker = 30, Dust = 30, Tape = 60, Size = 200, Effort = "best" },
    ];
}

/// <summary>The cut of one recording, so it comes back when the file is added again.</summary>
public sealed class ClipMemory
{
    [JsonPropertyName("size")] public long Size { get; set; }
    [JsonPropertyName("modified")] public long Modified { get; set; }
    [JsonPropertyName("segments")] public List<double[]> Segments { get; set; } = [];
    [JsonPropertyName("bookmarks")] public List<double> Bookmarks { get; set; } = [];
    [JsonPropertyName("seen")] public long Seen { get; set; }
}

/// <summary>
/// Choices the user should not have to repeat, kept in the per-user application
/// data folder. Missing or damaged files are ignored.
/// </summary>
public sealed class UserSettings
{
    [JsonPropertyName("outputFolder")] public string? OutputFolder { get; set; }
    [JsonPropertyName("outputSuffix")] public string OutputSuffix { get; set; } = "-repaired";
    [JsonPropertyName("outputFormat")] public string OutputFormat { get; set; } = "mp4-h264";
    [JsonPropertyName("openFolderAfterExport")] public bool OpenFolderAfterExport { get; set; } = true;
    [JsonPropertyName("joinClips")] public bool JoinClips { get; set; }
    [JsonPropertyName("snap")] public bool Snap { get; set; } = true;
    [JsonPropertyName("lastRepair")] public RepairPreset? LastRepair { get; set; }
    // The user's own presets; those saved by 0.1.0 load here unchanged.
    [JsonPropertyName("presets")] public List<RepairPreset> Presets { get; set; } = [];
    [JsonPropertyName("clips")] public Dictionary<string, ClipMemory> Clips { get; set; } = new();

    private const int RememberedClips = 300;
    private static readonly JsonSerializerOptions Options = new() { WriteIndented = true };

    public static string Folder()
    {
        var folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Analog Repair");
        Directory.CreateDirectory(folder);
        return folder;
    }

    public static string FilePath() => Path.Combine(Folder(), "settings.json");

    public static UserSettings Load()
    {
        try
        {
            var path = FilePath();
            if (File.Exists(path))
                return JsonSerializer.Deserialize<UserSettings>(File.ReadAllText(path), Options) ?? new UserSettings();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            // A broken settings file must never stop the app from starting.
        }
        return new UserSettings();
    }

    public void Save()
    {
        try
        {
            // Forget the cuts of recordings that have not been opened for a long time.
            if (Clips.Count > RememberedClips)
                foreach (var key in Clips.OrderBy(pair => pair.Value.Seen).Take(Clips.Count - RememberedClips).Select(pair => pair.Key).ToList())
                    Clips.Remove(key);
            var path = FilePath();
            var draft = path + ".tmp";
            File.WriteAllText(draft, JsonSerializer.Serialize(this, Options));
            File.Move(draft, path, overwrite: true);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Settings are a convenience; losing them is not worth an error dialog.
        }
    }

    public static string ClipKey(string path) =>
        OperatingSystem.IsWindows() ? Path.GetFullPath(path).ToLowerInvariant() : Path.GetFullPath(path);

    /// <summary>The remembered cut of a file, if the file is still the same one.</summary>
    public ClipMemory? RememberedCut(string path)
    {
        if (!Clips.TryGetValue(ClipKey(path), out var memory)) return null;
        try
        {
            var info = new FileInfo(path);
            if (info.Length != memory.Size || info.LastWriteTimeUtc.Ticks != memory.Modified) return null;
        }
        catch (IOException) { return null; }
        memory.Seen = DateTime.UtcNow.Ticks;
        return memory;
    }

    public void RememberCut(string path, IEnumerable<(double In, double Out)> segments, IEnumerable<double> bookmarks)
    {
        try
        {
            var info = new FileInfo(path);
            Clips[ClipKey(path)] = new ClipMemory
            {
                Size = info.Length, Modified = info.LastWriteTimeUtc.Ticks, Seen = DateTime.UtcNow.Ticks,
                Segments = segments.Select(s => new[] { s.In, s.Out }).ToList(),
                Bookmarks = bookmarks.ToList(),
            };
        }
        catch (IOException) { /* The file went away; nothing to remember. */ }
    }
}
