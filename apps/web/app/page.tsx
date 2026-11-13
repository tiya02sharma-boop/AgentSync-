import Link from 'next/link';

export default function Home() {
  return (
    <main className="home-page">
      <div className="home-wordmark">
        <span className="wordmark-signal">
          <i></i>
          <i></i>
          <i></i>
        </span>
        AgentSync
      </div>
      <section>
        <p>Conflict prevention for AI agent teams</p>
        <h1>
          Catch what breaks
          <br />
          before it lands.
        </h1>
        <span>
          AgentSync catches the logical conflicts Git cannot see, gets agents aligned through a
          human-approved contract, then verifies the combined work.
        </span>
        <Link href="/team/hackathon">Open the AgentSync room</Link>
      </section>
      <footer>Plan · monitor · resolve · verify</footer>
    </main>
  );
}
