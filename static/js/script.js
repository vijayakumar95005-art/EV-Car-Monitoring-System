(() => {
	const scene = document.getElementById("login-scene");
	const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
	const lowPerformance = (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2)
		|| (navigator.deviceMemory && navigator.deviceMemory <= 2);

	if (!scene || reducedMotion.matches || lowPerformance || !window.WebGLRenderingContext) {
		return;
	}

	let birds;
	try {
		if (!window.VANTA || !window.VANTA.BIRDS || !window.THREE) {
			return;
		}
		birds = window.VANTA.BIRDS({
			el: scene,
			THREE: window.THREE,
			mouseControls: true,
			touchControls: true,
			gyroControls: false,
			minHeight: 200,
			minWidth: 200,
			scale: 1,
			scaleMobile: 1,
			backgroundColor: 0x020b14,
			color1: 0xffb347,
			color2: 0x8be9fd,
			colorMode: "lerpGradient",
			birdSize: 0.8,
			separation: 56,
			alignment: 24,
			cohesion: 19,
			backgroundAlpha: 1
		});
	} catch (error) {
		return;
	}

	window.addEventListener("pagehide", () => {
		if (birds) {
			birds.destroy();
		}
	}, { once: true });
})();
