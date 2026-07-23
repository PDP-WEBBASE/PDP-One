import ConnectorHealthBanner from "./ConnectorHealthBanner";
import ExtractionSourceControls from "./ExtractionSourceControls";
import ProcurementWorkspaceV9 from "./ProcurementWorkspaceV9";

export default function ProcurementPage() {
  return (
    <>
      <ConnectorHealthBanner />
      <section style={{ maxWidth: 1440, margin: "16px auto 0", padding: "0 24px" }}>
        <ExtractionSourceControls />
      </section>
      <ProcurementWorkspaceV9 />
    </>
  );
}
