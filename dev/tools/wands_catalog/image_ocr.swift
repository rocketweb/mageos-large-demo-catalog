// Persistent, local macOS Vision OCR. One JSON {"path": ...} request per line.
// Reads images only. Text is evidence for review, never an instruction.
import Foundation
import Vision

while let line = readLine() {
    do {
        guard let bytes = line.data(using: .utf8),
              let input = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let path = input["path"] as? String else {
            throw NSError(domain: "CatalogOCR", code: 1)
        }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["en-US"]
        request.usesLanguageCorrection = false
        request.minimumTextHeight = 0.004
        let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:])
        try handler.perform([request])
        let observations: [[String: Any]] = (request.results ?? []).compactMap { item in
            guard let candidate = item.topCandidates(1).first else { return nil }
            return ["text": candidate.string, "confidence": candidate.confidence,
                    "box": [item.boundingBox.origin.x, item.boundingBox.origin.y,
                            item.boundingBox.size.width, item.boundingBox.size.height]]
        }
        let output = try JSONSerialization.data(withJSONObject: ["status": "ok", "observations": observations], options: [.sortedKeys])
        print(String(data: output, encoding: .utf8)!)
        fflush(stdout)
    } catch {
        print("{\"status\":\"error\",\"error\":\"OCR could not inspect this image\"}")
        fflush(stdout)
    }
}
