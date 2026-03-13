import Foundation
import Network
import Observation

/// Monitors network connectivity using `NWPathMonitor`.
///
/// Inject via `@Environment(NetworkMonitor.self)` at the app root.
/// Views can observe `isConnected` to show/hide the offline banner.
@Observable
final class NetworkMonitor {
    /// `true` when the device has a usable network path.
    var isConnected: Bool = true

    /// The current connection type (wifi, cellular, etc.).
    var connectionType: ConnectionType = .unknown

    enum ConnectionType: String {
        case wifi
        case cellular
        case wiredEthernet
        case unknown
    }

    private let monitor: NWPathMonitor
    private let queue: DispatchQueue

    init(monitor: NWPathMonitor = NWPathMonitor(), queue: DispatchQueue = DispatchQueue(label: "com.ember.networkMonitor")) {
        self.monitor = monitor
        self.queue = queue
    }

    /// Starts monitoring network path changes.
    /// Call once at app launch (e.g., in `EmberApp.init` or `.onAppear`).
    func start() {
        monitor.pathUpdateHandler = { [weak self] path in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.isConnected = path.status == .satisfied
                self.connectionType = self.mapConnectionType(path)
            }
        }
        monitor.start(queue: queue)
    }

    /// Stops monitoring. Call when no longer needed.
    func stop() {
        monitor.cancel()
    }

    // MARK: - Private

    private func mapConnectionType(_ path: NWPath) -> ConnectionType {
        if path.usesInterfaceType(.wifi) {
            return .wifi
        } else if path.usesInterfaceType(.cellular) {
            return .cellular
        } else if path.usesInterfaceType(.wiredEthernet) {
            return .wiredEthernet
        }
        return .unknown
    }
}
