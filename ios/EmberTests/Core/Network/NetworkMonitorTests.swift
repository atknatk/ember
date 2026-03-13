import Testing
import Foundation
@testable import Ember

@Suite("NetworkMonitor")
struct NetworkMonitorTests {

    @Test("initial state: isConnected is true")
    func initialState() {
        let monitor = NetworkMonitor()
        #expect(monitor.isConnected == true)
    }

    @Test("initial state: connectionType is unknown")
    func initialConnectionType() {
        let monitor = NetworkMonitor()
        #expect(monitor.connectionType == .unknown)
    }

    @Test("connectionType raw values are correct")
    func connectionTypeRawValues() {
        #expect(NetworkMonitor.ConnectionType.wifi.rawValue == "wifi")
        #expect(NetworkMonitor.ConnectionType.cellular.rawValue == "cellular")
        #expect(NetworkMonitor.ConnectionType.wiredEthernet.rawValue == "wiredEthernet")
        #expect(NetworkMonitor.ConnectionType.unknown.rawValue == "unknown")
    }

    @Test("stop does not crash when called before start")
    func stopBeforeStart() {
        let monitor = NetworkMonitor()
        // This should not crash
        monitor.stop()
    }
}
