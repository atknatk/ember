import AVFoundation
import Combine
import Observation

/// Manages audio playback for TTS messages.
/// Wraps AVPlayer with @Observable state for SwiftUI integration.
/// Enforces one-audio-at-a-time by stopping previous playback when a new one starts.
@Observable
final class AudioPlayerManager {
    // MARK: - Public State

    /// Whether audio is currently playing.
    var isPlaying: Bool = false

    /// The ID of the message currently being played (or paused).
    var currentMessageId: String? = nil

    /// Current playback position in seconds.
    var currentTime: Double = 0

    /// Total duration of the current audio in seconds.
    var duration: Double = 0

    /// Current playback speed.
    var playbackSpeed: Float = 1.0

    /// Whether the player is loading audio.
    var isLoading: Bool = false

    /// Error message from the last failed playback attempt.
    var playbackError: String? = nil

    // MARK: - Available Speeds

    /// Ordered list of playback speed options.
    static let availableSpeeds: [Float] = [0.75, 1.0, 1.25, 1.5]

    // MARK: - Private

    private var player: AVPlayer?
    private var timeObserver: Any?
    private var endObserver: NSObjectProtocol?
    private var statusCancellable: AnyCancellable?

    // MARK: - Init / Deinit

    init() {}

    deinit {
        cleanupObservers()
        player = nil
    }

    // MARK: - Public Methods

    /// Plays audio from the given URL. Stops any previously playing audio first.
    /// - Parameters:
    ///   - url: The URL of the audio file to play.
    ///   - messageId: The ID of the message this audio belongs to.
    func play(url: URL, messageId: String) {
        // If tapping the same message that is currently playing, toggle pause/resume
        if currentMessageId == messageId, let player {
            if isPlaying {
                player.pause()
                isPlaying = false
            } else {
                player.play()
                player.rate = playbackSpeed
                isPlaying = true
            }
            return
        }

        // Stop any current playback
        stop()

        // Configure audio session for playback
        configureAudioSession()

        // Set up new player
        isLoading = true
        playbackError = nil
        currentMessageId = messageId
        currentTime = 0
        duration = 0

        let playerItem = AVPlayerItem(url: url)
        player = AVPlayer(playerItem: playerItem)

        setupObservers(for: playerItem)

        player?.play()
        player?.rate = playbackSpeed
        isPlaying = true
    }

    /// Pauses the current playback.
    func pause() {
        player?.pause()
        isPlaying = false
    }

    /// Resumes playback if paused.
    func resume() {
        guard player != nil else { return }
        player?.play()
        player?.rate = playbackSpeed
        isPlaying = true
    }

    /// Stops playback and resets state.
    func stop() {
        cleanupObservers()
        player?.pause()
        player = nil
        isPlaying = false
        currentMessageId = nil
        currentTime = 0
        duration = 0
        isLoading = false
    }

    /// Cycles to the next playback speed in the available speeds list.
    func cycleSpeed() {
        guard let currentIndex = Self.availableSpeeds.firstIndex(of: playbackSpeed) else {
            playbackSpeed = 1.0
            player?.rate = playbackSpeed
            return
        }

        let nextIndex = (currentIndex + 1) % Self.availableSpeeds.count
        playbackSpeed = Self.availableSpeeds[nextIndex]

        if isPlaying {
            player?.rate = playbackSpeed
        }

        HapticManager.selection()
    }

    /// Sets the playback speed directly.
    func setSpeed(_ speed: Float) {
        guard Self.availableSpeeds.contains(speed) else { return }
        playbackSpeed = speed

        if isPlaying {
            player?.rate = playbackSpeed
        }
    }

    /// Seeks to a specific time position.
    func seek(to time: Double) {
        let cmTime = CMTime(seconds: time, preferredTimescale: 600)
        player?.seek(to: cmTime, toleranceBefore: .zero, toleranceAfter: .zero)
        currentTime = time
    }

    /// Returns true if this manager is currently handling the given message.
    func isActiveFor(messageId: String) -> Bool {
        currentMessageId == messageId
    }

    // MARK: - Private Helpers

    private func configureAudioSession() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .default)
            try session.setActive(true)
        } catch {
            // Audio session configuration failure is non-fatal; playback may still work
        }
    }

    private func setupObservers(for playerItem: AVPlayerItem) {
        // Periodic time observer for progress tracking (every 0.1 seconds)
        let interval = CMTime(seconds: 0.1, preferredTimescale: 600)
        timeObserver = player?.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] time in
            guard let self else { return }
            self.currentTime = time.seconds

            // Update duration when available
            let itemDuration = playerItem.duration
            if itemDuration.isValid && !itemDuration.isIndefinite {
                let totalSeconds = itemDuration.seconds
                if totalSeconds > 0 {
                    self.duration = totalSeconds
                    self.isLoading = false
                }
            }
        }

        // End-of-playback observer
        endObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime,
            object: playerItem,
            queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            self.isPlaying = false
            self.currentTime = 0
            self.player?.seek(to: .zero)
        }

        // Observe player item status for error handling and readyToPlay
        statusCancellable = playerItem.publisher(for: \.status)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] status in
                guard let self else { return }
                switch status {
                case .readyToPlay:
                    self.isLoading = false
                case .failed:
                    self.isLoading = false
                    self.isPlaying = false
                    self.playbackError = playerItem.error?.localizedDescription ?? "Playback failed"
                default:
                    break
                }
            }
    }

    private func cleanupObservers() {
        if let timeObserver {
            player?.removeTimeObserver(timeObserver)
        }
        timeObserver = nil

        if let endObserver {
            NotificationCenter.default.removeObserver(endObserver)
        }
        endObserver = nil

        statusCancellable?.cancel()
        statusCancellable = nil
    }
}
