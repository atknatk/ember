import Lottie
import SwiftUI

/// A thin UIViewRepresentable wrapper around Lottie's `LottieAnimationView`.
/// Plays the named animation from the bundle in loop mode.
/// If the animation JSON file is not found, the view renders as an empty frame.
struct LottieAnimationViewWrapper: UIViewRepresentable {
    let animationName: String
    var loopMode: LottieLoopMode = .loop

    func makeUIView(context: Context) -> UIView {
        let containerView = UIView(frame: .zero)
        containerView.backgroundColor = .clear

        guard let animation = LottieAnimation.named(animationName) else {
            return containerView
        }

        let animationView = LottieAnimationView(animation: animation)
        animationView.loopMode = loopMode
        animationView.contentMode = .scaleAspectFit
        animationView.translatesAutoresizingMaskIntoConstraints = false
        containerView.addSubview(animationView)

        NSLayoutConstraint.activate([
            animationView.leadingAnchor.constraint(equalTo: containerView.leadingAnchor),
            animationView.trailingAnchor.constraint(equalTo: containerView.trailingAnchor),
            animationView.topAnchor.constraint(equalTo: containerView.topAnchor),
            animationView.bottomAnchor.constraint(equalTo: containerView.bottomAnchor),
        ])

        animationView.play()

        return containerView
    }

    func updateUIView(_ uiView: UIView, context: Context) {}
}
