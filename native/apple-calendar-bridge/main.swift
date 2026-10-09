import EventKit
import Foundation

enum BridgeError: Error, LocalizedError {
    case invalidCommand
    case invalidPayload(String)
    case accessRequired
    case calendarUnavailable
    case eventNotFound

    var errorDescription: String? {
        switch self {
        case .invalidCommand: return "Commande EventKit inconnue."
        case .invalidPayload(let detail): return "Charge utile invalide : \(detail)"
        case .accessRequired: return "Accès complet au calendrier non accordé. Exécutez request-access."
        case .calendarUnavailable: return "Aucun calendrier Apple modifiable n’est disponible."
        case .eventNotFound: return "Événement Apple Calendar introuvable."
        }
    }
}

@main
struct AppleCalendarBridge {
    static let store = EKEventStore()
    static let iso = ISO8601DateFormatter()

    static func main() async {
        do {
            let arguments = CommandLine.arguments
            guard arguments.count >= 2 else { throw BridgeError.invalidCommand }
            let command = arguments[1]
            let payload = try parsePayload(arguments.count > 2 ? arguments[2] : nil)

            switch command {
            case "status":
                try output(status())
            case "request-access":
                let granted = try await store.requestFullAccessToEvents()
                try output(["authorization": granted ? "full_access" : "denied"])
            case "list":
                try requireAccess()
                try output(listEvents(payload))
            case "create":
                try requireAccess()
                try output(createEvent(payload))
            case "update":
                try requireAccess()
                try output(updateEvent(payload))
            case "delete":
                try requireAccess()
                try output(deleteEvent(payload))
            default:
                throw BridgeError.invalidCommand
            }
        } catch {
            FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
            Foundation.exit(1)
        }
    }

    static func authorizationName(_ status: EKAuthorizationStatus) -> String {
        switch status {
        case .notDetermined: return "not_determined"
        case .restricted: return "restricted"
        case .denied: return "denied"
        case .writeOnly: return "write_only"
        case .fullAccess: return "full_access"
        @unknown default: return "unknown"
        }
    }

    static func status() -> [String: Any] {
        let authorization = EKEventStore.authorizationStatus(for: .event)
        return [
            "authorization": authorizationName(authorization),
            "calendar_count": authorization == .fullAccess ? store.calendars(for: .event).count : 0,
        ]
    }

    static func requireAccess() throws {
        guard EKEventStore.authorizationStatus(for: .event) == .fullAccess else {
            throw BridgeError.accessRequired
        }
    }

    static func parsePayload(_ raw: String?) throws -> [String: Any] {
        guard let raw else { return [:] }
        guard let data = raw.data(using: .utf8),
              let value = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw BridgeError.invalidPayload("JSON attendu")
        }
        return value
    }

    static func calendar(_ payload: [String: Any]) throws -> EKCalendar {
        if let identifier = payload["calendar_identifier"] as? String, !identifier.isEmpty,
           let selected = store.calendar(withIdentifier: identifier) {
            return selected
        }
        guard let fallback = store.defaultCalendarForNewEvents else {
            throw BridgeError.calendarUnavailable
        }
        return fallback
    }

    static func listEvents(_ payload: [String: Any]) throws -> [[String: Any]] {
        guard let day = payload["date"] as? String else {
            throw BridgeError.invalidPayload("date requise")
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = .current
        formatter.dateFormat = "yyyy-MM-dd"
        guard let start = formatter.date(from: day),
              let end = Calendar.current.date(byAdding: .day, value: 1, to: start) else {
            throw BridgeError.invalidPayload("date incorrecte")
        }
        let calendars: [EKCalendar]?
        if let identifier = payload["calendar_identifier"] as? String, !identifier.isEmpty,
           let selected = store.calendar(withIdentifier: identifier) {
            calendars = [selected]
        } else {
            calendars = nil
        }
        let predicate = store.predicateForEvents(withStart: start, end: end, calendars: calendars)
        return store.events(matching: predicate).map(eventPayload)
    }

    static func createEvent(_ payload: [String: Any]) throws -> [String: Any] {
        let event = EKEvent(eventStore: store)
        event.calendar = try calendar(payload)
        try apply(payload, to: event, requiresDates: true)
        try store.save(event, span: .thisEvent, commit: true)
        return eventPayload(event)
    }

    static func updateEvent(_ payload: [String: Any]) throws -> [String: Any] {
        guard let identifier = payload["event_id"] as? String,
              let event = store.event(withIdentifier: identifier) else {
            throw BridgeError.eventNotFound
        }
        try apply(payload, to: event, requiresDates: false)
        try store.save(event, span: .thisEvent, commit: true)
        return eventPayload(event)
    }

    static func deleteEvent(_ payload: [String: Any]) throws -> [String: Any] {
        guard let identifier = payload["event_id"] as? String,
              let event = store.event(withIdentifier: identifier) else {
            throw BridgeError.eventNotFound
        }
        let snapshot = eventPayload(event)
        try store.remove(event, span: .thisEvent, commit: true)
        return snapshot
    }

    static func apply(_ payload: [String: Any], to event: EKEvent, requiresDates: Bool) throws {
        if let title = payload["title"] as? String { event.title = title }
        if let location = payload["location"] as? String { event.location = location }
        if let notes = payload["notes"] as? String { event.notes = notes }
        if let raw = payload["starts_at"] as? String, let value = iso.date(from: raw) {
            event.startDate = value
        } else if requiresDates {
            throw BridgeError.invalidPayload("starts_at requis")
        }
        if let raw = payload["ends_at"] as? String, let value = iso.date(from: raw) {
            event.endDate = value
        } else if requiresDates {
            throw BridgeError.invalidPayload("ends_at requis")
        }
    }

    static func eventPayload(_ event: EKEvent) -> [String: Any] {
        [
            "id": event.eventIdentifier ?? "",
            "title": event.title ?? "Sans titre",
            "starts_at": iso.string(from: event.startDate),
            "ends_at": iso.string(from: event.endDate),
            "location": event.location ?? "",
            "notes": event.notes ?? "",
            "source": "apple",
            "calendar": event.calendar.title,
        ]
    }

    static func output(_ value: Any) throws {
        let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))
    }
}
