// Translates texts with the macOS Translation framework (on-device, free, offline).
// Requires macOS 26+ and the language packs installed in
// System Settings → General → Language & Region → Translation Languages.
//
// stdin:  {"src": "en", "tgt": "ru", "texts": ["...", ...]}
// stdout: {"translations": ["...", ...]}
// exit 3: language pack not installed; exit 4: language pair not supported; exit 1: other error.
import Foundation
import Translation

struct Input: Decodable { let src: String; let tgt: String; let texts: [String] }
struct Output: Encodable { let translations: [String] }

func fail(_ code: Int32, _ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(code)
}

let data = FileHandle.standardInput.readDataToEndOfFile()
guard let input = try? JSONDecoder().decode(Input.self, from: data) else {
    fail(1, "bad input JSON")
}
let src = Locale.Language(identifier: input.src)
let tgt = Locale.Language(identifier: input.tgt)

switch await LanguageAvailability().status(from: src, to: tgt) {
case .installed: break
case .supported: fail(3, "not installed: \(input.src)->\(input.tgt)")
case .unsupported: fail(4, "unsupported: \(input.src)->\(input.tgt)")
@unknown default: break
}

let session = TranslationSession(installedSource: src, target: tgt)
var result = [String](repeating: "", count: input.texts.count)
let chunk = 50
do {
    for start in stride(from: 0, to: input.texts.count, by: chunk) {
        let end = min(start + chunk, input.texts.count)
        let requests = (start..<end).map {
            TranslationSession.Request(sourceText: input.texts[$0], clientIdentifier: String($0))
        }
        for r in try await session.translations(from: requests) {
            if let id = r.clientIdentifier, let i = Int(id) { result[i] = r.targetText }
        }
        FileHandle.standardError.write("  translated \(end)/\(input.texts.count)\n".data(using: .utf8)!)
    }
} catch {
    fail(1, "translation failed: \(error)")
}

let out = try! JSONEncoder().encode(Output(translations: result))
FileHandle.standardOutput.write(out)
