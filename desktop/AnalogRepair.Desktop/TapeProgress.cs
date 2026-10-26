using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Threading;

namespace AnalogRepair.Desktop;

/// <summary>
/// A progress bar with a tape in it: a gradient track that fills up, a light
/// that sweeps along it, and a small video cassette that rides on the tip with
/// its reels turning. In the indeterminate state the cassette travels to and fro.
/// </summary>
public sealed class TapeProgress : Control
{
    public static readonly StyledProperty<double> ValueProperty =
        AvaloniaProperty.Register<TapeProgress, double>(nameof(Value));
    public static readonly StyledProperty<bool> IsIndeterminateProperty =
        AvaloniaProperty.Register<TapeProgress, bool>(nameof(IsIndeterminate), true);

    private static readonly IBrush TrackBrush = new SolidColorBrush(Color.Parse("#ECEDEA"));
    private readonly DispatcherTimer _clock = new() { Interval = TimeSpan.FromMilliseconds(33) };
    private double _time;

    public TapeProgress()
    {
        Height = 48;
        ClipToBounds = false;
        _clock.Tick += (_, _) => { _time += 0.033; InvalidateVisual(); };
        AttachedToVisualTree += (_, _) => _clock.Start();
        DetachedFromVisualTree += (_, _) => _clock.Stop();
    }

    /// <summary>0 to 100.</summary>
    public double Value { get => GetValue(ValueProperty); set => SetValue(ValueProperty, value); }
    public bool IsIndeterminate { get => GetValue(IsIndeterminateProperty); set => SetValue(IsIndeterminateProperty, value); }

    public override void Render(DrawingContext context)
    {
        var width = Bounds.Width;
        if (width <= 0) return;
        const double trackHeight = 10;
        var trackTop = Bounds.Height - trackHeight - 2;
        var track = new Rect(0, trackTop, width, trackHeight);
        context.DrawRectangle(TrackBrush, null, new RoundedRect(track, trackHeight / 2));

        // Where the tip is: the real value, or a patrol between the ends.
        var fraction = IsIndeterminate ? 0.5 + 0.5 * Math.Sin(_time * 1.6) : Math.Clamp(Value / 100, 0, 1);
        var tipX = fraction * width;

        if (IsIndeterminate)
        {
            // A soft trail behind the travelling cassette.
            var direction = Math.Cos(_time * 1.6) >= 0 ? 1 : -1;
            var trailStart = Math.Clamp(tipX - direction * 90, 0, width);
            var trail = new Rect(Math.Min(tipX, trailStart), trackTop, Math.Abs(tipX - trailStart), trackHeight);
            var trailBrush = new LinearGradientBrush
            {
                StartPoint = new RelativePoint(direction > 0 ? 0 : 1, 0, RelativeUnit.Relative),
                EndPoint = new RelativePoint(direction > 0 ? 1 : 0, 0, RelativeUnit.Relative),
                GradientStops = { new GradientStop(Color.Parse("#00F08A3A"), 0), new GradientStop(Color.Parse("#F08A3A"), 1) },
            };
            if (trail.Width > 1) context.DrawRectangle(trailBrush, null, new RoundedRect(trail, trackHeight / 2));
        }
        else if (tipX > 1)
        {
            var fill = new Rect(0, trackTop, tipX, trackHeight);
            var fillBrush = new LinearGradientBrush
            {
                StartPoint = new RelativePoint(0, 0, RelativeUnit.Relative),
                EndPoint = new RelativePoint(1, 0, RelativeUnit.Relative),
                GradientStops = { new GradientStop(Color.Parse("#A64600"), 0), new GradientStop(Color.Parse("#F08A3A"), 0.7), new GradientStop(Color.Parse("#FFC857"), 1) },
            };
            context.DrawRectangle(fillBrush, null, new RoundedRect(fill, trackHeight / 2));
            // A light sweeping along the filled part.
            var sweep = (_time * 0.45) % 1.3 - 0.15;
            var lightX = sweep * tipX;
            var light = new Rect(lightX - 18, trackTop, 36, trackHeight);
            var lightBrush = new LinearGradientBrush
            {
                StartPoint = new RelativePoint(0, 0, RelativeUnit.Relative),
                EndPoint = new RelativePoint(1, 0, RelativeUnit.Relative),
                GradientStops = { new GradientStop(Color.Parse("#00FFFFFF"), 0), new GradientStop(Color.Parse("#90FFFFFF"), 0.5), new GradientStop(Color.Parse("#00FFFFFF"), 1) },
            };
            using (context.PushClip(new RoundedRect(fill, trackHeight / 2)))
                context.DrawRectangle(lightBrush, null, light);
        }

        DrawCassette(context, Math.Clamp(tipX, 22, width - 22), trackTop - 16);
    }


    private static readonly IBrush ShellBrush = new SolidColorBrush(Color.Parse("#2C3238"));
    private static readonly IBrush EdgeBrush = new SolidColorBrush(Color.Parse("#1B2025"));
    private static readonly IBrush LabelBrush = new SolidColorBrush(Color.Parse("#F3E3C7"));
    private static readonly IBrush StripeBrush = new SolidColorBrush(Color.Parse("#F08A3A"));
    private static readonly IBrush StripeDarkBrush = new SolidColorBrush(Color.Parse("#A64600"));
    private static readonly IBrush WindowBrush = new SolidColorBrush(Color.Parse("#5B4636"));
    private static readonly IBrush TapeBrush = new SolidColorBrush(Color.Parse("#3A2A20"));
    private static readonly IBrush HubBrush = new SolidColorBrush(Color.Parse("#F3F3F0"));
    private static readonly IBrush ShadowBrush = new SolidColorBrush(Color.Parse("#30000000"));
    private static readonly Typeface Face = new("Inter, Segoe UI, Helvetica, Arial");

    /// <summary>
    /// A small video cassette riding on the tip: dark shell, a cream label with
    /// an orange stripe, and a window in which two reels turn. The left reel
    /// gives tape and shrinks as the bar fills, the right one takes it up and
    /// grows. It bobs a little and casts a shadow on the track.
    /// </summary>
    private void DrawCassette(DrawingContext context, double x, double y)
    {
        const double scale = 1.3;
        using var _ = context.PushTransform(Matrix.CreateTranslation(-x, -y) * Matrix.CreateScale(scale, scale) * Matrix.CreateTranslation(x, y));
        var bob = Math.Sin(_time * 4) * 1.5;
        y += bob;
        var shadowScale = 1 - (bob + 1.5) / 10;
        context.DrawEllipse(ShadowBrush, null, new Point(x, y + 13), 14 * shadowScale, 2 * shadowScale);

        // Shell and label.
        context.DrawRectangle(ShellBrush, new Pen(EdgeBrush, 0.8), new RoundedRect(new Rect(x - 15, y - 9.5, 30, 19), 2.2));
        context.DrawRectangle(LabelBrush, null, new RoundedRect(new Rect(x - 12.5, y - 7.5, 25, 10.5), 1.2));
        context.DrawRectangle(StripeBrush, null, new Rect(x - 12.5, y - 6.3, 25, 1.6));
        context.DrawRectangle(StripeDarkBrush, null, new Rect(x - 12.5, y - 4.4, 25, 0.8));
        // The tape window with the two reels.
        var window = new Rect(x - 9, y - 2.6, 18, 5.2);
        context.DrawRectangle(WindowBrush, null, new RoundedRect(window, 2.6));
        var fill = IsIndeterminate ? 0.5 + 0.35 * Math.Sin(_time * 0.7) : Math.Clamp(Value / 100, 0, 1);
        var spin = _time * 7;
        DrawReel(context, new Point(x - 5.2, y), 1.6 + 1.3 * (1 - fill), spin);
        DrawReel(context, new Point(x + 5.2, y), 1.6 + 1.3 * fill, spin + 0.6);
        // The guide slot at the bottom edge, where the tape runs past the heads.
        context.DrawRectangle(EdgeBrush, null, new Rect(x - 8, y + 6.6, 16, 1.4));

        if (!IsIndeterminate)
        {
            var label = new FormattedText($"{Math.Clamp(Value, 0, 100):0} %", System.Globalization.CultureInfo.InvariantCulture,
                FlowDirection.LeftToRight, new Typeface(Face.FontFamily, FontStyle.Normal, FontWeight.SemiBold), 11, ShellBrush);
            var labelX = x + 19 + label.Width > Bounds.Width ? x - 19 - label.Width : x + 19;
            context.DrawText(label, new Point(labelX, y - 7));
        }
    }

    /// <summary>One reel: the wound tape, a white hub and three turning spokes.</summary>
    private static void DrawReel(DrawingContext context, Point centre, double tape, double angle)
    {
        context.DrawEllipse(TapeBrush, null, centre, tape, tape);
        context.DrawEllipse(HubBrush, null, centre, 1.25, 1.25);
        var spoke = new Pen(ShellBrush, 0.5, lineCap: PenLineCap.Round);
        for (var i = 0; i < 3; i++)
        {
            var a = angle + i * Math.PI * 2 / 3;
            context.DrawLine(spoke, centre, new Point(centre.X + Math.Cos(a) * 1.2, centre.Y + Math.Sin(a) * 1.2));
        }
    }
}
