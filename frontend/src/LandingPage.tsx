import { useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import { ArrowDown, ArrowRight, CalendarCheck, HeartHandshake, Leaf, Pill, ScanSearch, ShieldCheck, Stethoscope } from 'lucide-react'
import { HelpingHands } from './HelpingHands'
import './landing-page.css'

type LandingPageProps = { onGetStarted: () => void; onSignIn: () => void }

const journey = [
  { icon: HeartHandshake, who: 'The donor', line: 'Someone opens a cupboard and finds sealed medicine they no longer need. Instead of letting it expire, they share it.' },
  { icon: Stethoscope, who: 'The clinic pharmacist', line: 'A pharmacist inspects every donation — packaging, batch, expiry — and approves only what is safe.' },
  { icon: Pill, who: 'The patient', line: 'A person who needs that medicine requests it with their prescription, and collects it with dignity.' },
]
const checks = [
  { icon: ScanSearch, title: 'Inspected by a pharmacist', detail: 'Every donated medicine is reviewed before it is listed for anyone.' },
  { icon: CalendarCheck, title: 'Expiry and packaging checked', detail: 'Opened, damaged or near-expiry medicine is set aside, not shared.' },
  { icon: ShieldCheck, title: 'Prescriptions verified', detail: 'Eligible patients receive medicine only after their prescription is confirmed.' },
]

function useLandingMotion() {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const root = ref.current
    if (!root) return
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const reveals = root.querySelectorAll<HTMLElement>('.ml-reveal')
    let observer: IntersectionObserver | undefined
    if (reduceMotion || !('IntersectionObserver' in window)) {
      reveals.forEach((element) => element.classList.add('is-visible'))
    } else {
      observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible')
          observer?.unobserve(entry.target)
        }
      }), { threshold: 0.15 })
      reveals.forEach((element) => observer?.observe(element))
    }

    let frame = 0
    const onScroll = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => root.style.setProperty('--ml-scroll', String(Math.min(window.scrollY, 1400))))
    }
    if (!reduceMotion) window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      observer?.disconnect()
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(frame)
    }
  }, [])
  return ref
}

export default function LandingPage({ onGetStarted, onSignIn }: LandingPageProps) {
  const ref = useLandingMotion()
  return <div ref={ref} className="medshare-landing">
    <header className="ml-header">
      <a className="ml-brand" href="#home" aria-label="MedShare AI home"><span className="ml-brand-mark"><HeartHandshake size={20} /></span><span>medshare<span className="ml-brand-ai">ai</span></span></a>
      <nav aria-label="Main navigation"><a className="ml-nav-link" href="#journey">How it works</a><a className="ml-nav-link" href="#safety">Safety</a><button className="ml-button ml-button-primary" onClick={onSignIn}>Sign in</button></nav>
    </header>

    <main id="home">
      <section className="ml-hero">
        <div className="ml-hero-copy ml-rise">
          <p className="ml-eyebrow">People helping people</p>
          <h1 className="ml-title">Pass on medicine.<span>Pass on hope.</span></h1>
          <p className="ml-subtitle">Sealed, unused medicine sitting in a drawer could ease someone's pain tomorrow. MedShare AI connects generous donors with trusted pharmacists and the patients who need care.</p>
          <div className="ml-hero-actions"><button className="ml-button ml-button-primary ml-button-large" onClick={onGetStarted}>Get Started <ArrowRight size={17} /></button><a className="ml-discover" href="#journey">Discover How It Works <ArrowDown size={16} /></a></div>
        </div>
        <div className="ml-hero-art ml-rise ml-parallax" style={{ '--ml-depth': '-0.06' } as CSSProperties}>
          <span className="ml-blob" aria-hidden="true" /><HelpingHands />
          <p className="ml-handwritten">From one pair of hands to another.</p>
        </div>
      </section>

      <section id="journey" className="ml-story-band">
        <div className="ml-section-inner">
          <div className="ml-reveal ml-narrow"><p className="ml-eyebrow">The medicine journey</p><h2 className="ml-heading">One box. Three pairs of hands.</h2></div>
          <div className="ml-journey">
            <svg className="ml-journey-svg" viewBox="0 0 1000 120" preserveAspectRatio="none" aria-hidden="true"><path d="M60 60 C 260 -10, 340 130, 500 60 S 760 -10, 940 60" className="ml-journey-line" /><circle r="9"><animateMotion dur="7s" repeatCount="indefinite" path="M60 60 C 260 -10, 340 130, 500 60 S 760 -10, 940 60" /></circle></svg>
            <ol>{journey.map((step, index) => <li className="ml-reveal ml-journey-step" key={step.who} style={{ transitionDelay: `${index * 140}ms` }}>
              <span className="ml-journey-node"><step.icon size={28} strokeWidth={1.3} /></span><span className="ml-step-label">Step {index + 1}</span><h3>{step.who}</h3><p>{step.line}</p>
            </li>)}</ol>
          </div>
        </div>
      </section>

      <section id="safety" className="ml-safety ml-section-inner">
        <div className="ml-reveal"><p className="ml-eyebrow">Trust and safety</p><h2 className="ml-heading">Kindness, checked by experts.</h2><p className="ml-subtitle">Generosity only helps when it's safe. That's why a clinic pharmacist verifies each donated medicine before any eligible patient can access it.</p>
          <svg viewBox="0 0 200 200" className="ml-seal" aria-hidden="true"><circle cx="100" cy="100" r="78" className="ml-art-outline ml-seal-ring"/><path d="M100 42 148 62v40c0 30-22 50-48 58-26-8-48-28-48-58V62Z" className="ml-art-sage"/><path d="m76 102 17 17 33-36" className="ml-art-outline ml-seal-tick"/></svg>
        </div>
        <ul className="ml-safety-list">{checks.map((check, index) => <li className="ml-reveal ml-safety-row" key={check.title} style={{ transitionDelay: `${index * 120}ms` }}><check.icon size={25} strokeWidth={1.4} /><div><h3>{check.title}</h3><p>{check.detail}</p></div></li>)}</ul>
      </section>

      <section className="ml-impact"><div className="ml-section-inner ml-impact-inner">
        <div className="ml-reveal ml-impact-art ml-parallax" style={{ '--ml-depth': '0.04' } as CSSProperties}>
          <svg viewBox="0 0 420 300" role="img" aria-label="Two neighbours sharing a small parcel beside a growing plant">
            <path d="M40 250c20-120 120-190 220-170 90 18 140 90 120 170Z" className="ml-art-sage"/><circle cx="150" cy="120" r="28" className="ml-art-sand ml-art-outline"/><path d="M110 250c0-60 20-95 40-95s40 35 40 95Z" className="ml-art-terra"/><circle cx="275" cy="112" r="28" className="ml-art-sand ml-art-outline"/><path d="M235 250c0-62 20-100 40-100s40 38 40 100Z" className="ml-art-charcoal"/><g className="ml-parcel"><rect x="194" y="168" width="38" height="28" rx="4" className="ml-art-cream ml-art-outline"/><path d="M213 168v28" className="ml-art-outline"/></g><path d="M360 250v-60m0 22c-20-4-22-20-22-20 14-2 22 8 22 20Zm0-12c18-6 20-22 20-22-14 0-20 10-20 22Z" className="ml-art-outline ml-leaf-draw"/><path d="M213 70c-14-14-24 4 0 18 24-14 14-32 0-18Z" className="ml-art-terra ml-heart-small"/>
          </svg>
        </div>
        <div className="ml-reveal"><p className="ml-eyebrow">Human impact</p><h2 className="ml-heading">Relief shouldn't depend on what you can afford.</h2><p className="ml-subtitle">For many families, the cost of medicine means hard choices. A shared box of tablets can mean finishing a treatment, sleeping through the night, or simply feeling that someone cared.</p><p className="ml-handwritten ml-impact-note">Small acts. Real comfort. A neighbourhood that looks after its own.</p></div>
      </div></section>

      <section className="ml-final-cta ml-reveal"><Leaf size={32} strokeWidth={1.3} /><h2 className="ml-heading">Ready to lend a hand?</h2><p className="ml-subtitle">Donate, request, verify or oversee — choose the role that fits you and explore the platform.</p><div><button className="ml-button ml-button-primary ml-button-large" onClick={onGetStarted}>Get Started <ArrowRight size={17} /></button><button className="ml-button ml-button-ghost" onClick={onSignIn}>Sign In</button></div></section>
    </main>

    <footer className="ml-footer"><a className="ml-brand" href="#home"><span className="ml-brand-mark"><HeartHandshake size={20} /></span><span>medshare<span className="ml-brand-ai">ai</span></span></a><nav aria-label="Footer navigation"><a className="ml-nav-link" href="#journey">How it works</a><a className="ml-nav-link" href="#safety">Safety</a><button className="ml-footer-link" onClick={onSignIn}>Sign in</button></nav><span>Carefully shared. Professionally reviewed.</span></footer>
  </div>
}
