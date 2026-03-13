import AVFoundation
import Observation
import UIKit

/// Wraps AVAudioRecorder to provide voice recording with audio level metering.
///
/// Uses `@Observable` (iOS 17+) for state management.
/// Records in M4A (AAC) format at 44100 Hz mono, with a 2-minute maximum duration.
@Observable
final class VoiceRecorder: NSObject {
    // MARK: - Public State

    /// Whether a recording is currently in progress.
    private(set) var isRecording: Bool = false

    /// Elapsed recording duration in seconds.
    private(set) var recordingDuration: TimeInterval = 0

    /// Normalized audio levels (0.0 to 1.0) for waveform visualization.
    /// Updated at ~15 Hz while recording.
    private(set) var audioLevels: [CGFloat] = Array(repeating: 0, count: 24)

    /// Whether the user has granted microphone permission.
    private(set) var permissionGranted: Bool = false

    /// Whether the user has explicitly denied microphone permission.
    private(set) var permissionDenied: Bool = false

    /// Whether the recorder is currently processing (uploading + transcribing).
    private(set) var isProcessing: Bool = false

    // MARK: - Private

    private var audioRecorder: AVAudioRecorder?
    private var meteringTimer: Timer?
    private var durationTimer: Timer?
    private var recordingURL: URL?

    /// Maximum recording duration in seconds.
    private let maxDuration: TimeInterval = 120

    /// Number of waveform bars to maintain.
    private let levelCount: Int = 24

    // MARK: - Permission

    /// Requests microphone permission. Must be called before `startRecording()`.
    /// Updates `permissionGranted` and `permissionDenied` state.
    func requestPermission() async {
        if #available(iOS 17, *) {
            let granted = await AVAudioApplication.requestRecordPermission()
            await MainActor.run {
                self.permissionGranted = granted
                self.permissionDenied = !granted
            }
        } else {
            await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
                AVAudioSession.sharedInstance().requestRecordPermission { granted in
                    Task { @MainActor in
                        self.permissionGranted = granted
                        self.permissionDenied = !granted
                        continuation.resume()
                    }
                }
            }
        }
    }

    /// Checks the current microphone authorization status without prompting.
    func checkPermissionStatus() {
        let status = AVAudioSession.sharedInstance().recordPermission
        switch status {
        case .granted:
            permissionGranted = true
            permissionDenied = false
        case .denied:
            permissionGranted = false
            permissionDenied = true
        case .undetermined:
            permissionGranted = false
            permissionDenied = false
        @unknown default:
            permissionGranted = false
            permissionDenied = false
        }
    }

    // MARK: - Recording

    /// Starts recording audio. Returns `false` if setup fails.
    @discardableResult
    func startRecording() -> Bool {
        guard permissionGranted else { return false }
        guard !isRecording else { return false }

        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.record, mode: .default, options: [])
            try session.setActive(true)
        } catch {
            return false
        }

        let url = makeRecordingURL()
        recordingURL = url

        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 44100.0,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]

        do {
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            recorder.delegate = self
            recorder.isMeteringEnabled = true

            guard recorder.prepareToRecord(), recorder.record() else {
                return false
            }

            audioRecorder = recorder
            isRecording = true
            recordingDuration = 0
            audioLevels = Array(repeating: 0, count: levelCount)

            startMeteringTimer()
            startDurationTimer()

            return true
        } catch {
            return false
        }
    }

    /// Stops the current recording and returns the URL of the recorded file.
    /// Returns `nil` if no recording was in progress.
    func stopRecording() -> URL? {
        guard isRecording, let recorder = audioRecorder else { return nil }

        recorder.stop()
        stopTimers()
        isRecording = false

        deactivateAudioSession()

        return recordingURL
    }

    /// Cancels the current recording and deletes the file.
    func cancelRecording() {
        guard isRecording, let recorder = audioRecorder else { return }

        recorder.stop()
        recorder.deleteRecording()
        stopTimers()
        isRecording = false
        recordingURL = nil
        audioLevels = Array(repeating: 0, count: levelCount)

        deactivateAudioSession()
    }

    /// Cleans up a temporary recording file after it has been processed.
    func cleanupRecordingFile(at url: URL) {
        try? FileManager.default.removeItem(at: url)
    }

    // MARK: - Private Helpers

    private func makeRecordingURL() -> URL {
        let tempDir = FileManager.default.temporaryDirectory
        let filename = "voice_\(UUID().uuidString).m4a"
        return tempDir.appendingPathComponent(filename)
    }

    private func startMeteringTimer() {
        meteringTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 15.0, repeats: true) { [weak self] _ in
            self?.updateMetering()
        }
    }

    private func startDurationTimer() {
        durationTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.recordingDuration += 0.1

            // Auto-stop at max duration
            if self.recordingDuration >= self.maxDuration {
                _ = self.stopRecording()
            }
        }
    }

    private func stopTimers() {
        meteringTimer?.invalidate()
        meteringTimer = nil
        durationTimer?.invalidate()
        durationTimer = nil
    }

    private func updateMetering() {
        guard let recorder = audioRecorder, recorder.isRecording else { return }

        recorder.updateMeters()

        // AVAudioRecorder returns dB values: -160 (silence) to 0 (max).
        // Normalize to 0.0 - 1.0 range.
        let dB = recorder.averagePower(forChannel: 0)
        let normalizedLevel = normalizeDecibels(dB)

        // Shift levels left, append new level
        var newLevels = audioLevels
        newLevels.removeFirst()
        newLevels.append(normalizedLevel)
        audioLevels = newLevels
    }

    /// Converts a decibel value (-160 to 0) to a normalized level (0.0 to 1.0).
    private func normalizeDecibels(_ dB: Float) -> CGFloat {
        let minDB: Float = -60
        let maxDB: Float = 0

        let clamped = max(minDB, min(maxDB, dB))
        let normalized = (clamped - minDB) / (maxDB - minDB)
        return CGFloat(normalized)
    }

    private func deactivateAudioSession() {
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
}

// MARK: - AVAudioRecorderDelegate

extension VoiceRecorder: AVAudioRecorderDelegate {
    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        if !flag {
            // Recording failed (e.g., disk full, interrupted)
            isRecording = false
            stopTimers()
            recordingURL = nil
        }
    }

    func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: Error?) {
        isRecording = false
        stopTimers()
        recordingURL = nil
    }
}
