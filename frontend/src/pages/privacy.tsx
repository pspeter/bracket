import { Anchor, Container, List, Stack, Text, Title } from '@mantine/core';

export default function PrivacyPage() {
  return (
    <Container size="sm" py="xl">
      <Stack gap="lg">
        <Title order={1}>Impressum & Datenschutz</Title>

        <Stack gap="sm">
          <Title order={2}>Impressum</Title>
          <Text>
            Diensteanbieter und Verantwortlicher im Sinne der DSGVO sowie Medieninhaber gemäß § 5
            E-Commerce-Gesetz (ECG):
          </Text>
          <Text>
            Sportverein Aufschlag
            <br />
            Linke Wienzeile 102
            <br />
            1060 Wien, Österreich
            <br />
            ZVR-Zahl: 315544772
          </Text>
          <Text>
            Tel.: +43 660 2844913
            <br />
            E-Mail: <Anchor href="mailto:maud@aufschlag.org">maud@aufschlag.org</Anchor> (Maud Böhm)
          </Text>
        </Stack>

        <Stack gap="sm">
          <Title order={2}>Datenschutzhinweise</Title>
          <Text>
            Wir verarbeiten personenbezogene Daten nach der Datenschutz-Grundverordnung (DSGVO) und
            dem österreichischen Datenschutzgesetz (DSG). Diese Hinweise erklären, welche Daten wir
            wofür verarbeiten und welche Rechte du als betroffene Person hast.
          </Text>

          <Title order={3}>1. Verantwortlicher</Title>
          <Text>
            Verantwortlich für die Datenverarbeitung ist der oben genannte Sportverein Aufschlag.
            Für Fragen zum Datenschutz wende dich bitte an die im Impressum angegebene
            E-Mail-Adresse.
          </Text>

          <Title order={3}>2. Welche Daten wir verarbeiten</Title>
          <List withPadding>
            <List.Item>
              <strong>Anmeldedaten zum Turnier:</strong> Spielername, optional gewählter oder
              angelegter Teamname sowie Spielstärke/Level. Diese Daten gibst du selbst über das
              Anmeldeformular ein.
            </List.Item>
            <List.Item>
              <strong>Turnierdaten:</strong> Zugehörigkeit zu Teams, Spielpaarungen und Ergebnisse,
              die im Lauf des Turniers entstehen.
            </List.Item>
            <List.Item>
              <strong>Server-Protokolldaten:</strong> Beim Aufruf der Website werden technische
              Daten (IP-Adresse, Zeitpunkt, abgerufene Ressource, User-Agent) automatisch erfasst,
              wie es bei jedem Webserver üblich ist.
            </List.Item>
            <List.Item>
              <strong>Organisator-Konto:</strong> Für die Vereinsadministration verwenden wir
              persönliche Konten (E-Mail, Passwort-Hash). Spieler benötigen kein Konto.
            </List.Item>
          </List>
          <Text>
            Wir verwenden keine Tracking-Cookies, kein Analyse-Tool und keine Werbenetzwerke. Beim
            Anmeldeformular werden keine Cookies gesetzt.
          </Text>

          <Title order={3}>3. Zwecke und Rechtsgrundlagen</Title>
          <List withPadding>
            <List.Item>
              <strong>Anmelde- und Turnierdaten</strong> verarbeiten wir zur Durchführung des
              Turniers, an dem du teilnimmst. Rechtsgrundlage ist die Erfüllung des
              (vereinsrechtlichen) Teilnahmeverhältnisses gemäß Art. 6 Abs. 1 lit. b DSGVO. Die
              Veröffentlichung von Spielplänen, Ergebnissen und Tabellen auf dem öffentlichen
              Dashboard ist ein integraler Bestandteil der Turnierteilnahme.
            </List.Item>
            <List.Item>
              <strong>Server-Protokolldaten</strong> verarbeiten wir zur Sicherstellung des
              ordnungsgemäßen Betriebs und zur Abwehr von Missbrauch. Rechtsgrundlage ist unser
              berechtigtes Interesse gemäß Art. 6 Abs. 1 lit. f DSGVO.
            </List.Item>
            <List.Item>
              <strong>Organisator-Konten</strong> verarbeiten wir zur Verwaltung der Turniere.
              Rechtsgrundlage ist die Erfüllung des Vereinsmitgliedschafts- bzw.
              Funktionsverhältnisses gemäß Art. 6 Abs. 1 lit. b DSGVO.
            </List.Item>
          </List>

          <Title order={3}>4. Empfänger der Daten</Title>
          <Text>
            Die Daten werden ausschließlich auf einem vom Verein selbst betriebenen Server in
            Österreich gespeichert. Es findet keine Übermittlung an Dritte und keine Übermittlung in
            Drittländer (außerhalb der EU/EWR) statt. Auftragsverarbeiter werden nicht eingesetzt.
          </Text>

          <Title order={3}>5. Speicherdauer</Title>
          <List withPadding>
            <List.Item>
              <strong>Anmelde- und Turnierdaten</strong> bleiben Teil der Vereinschronik und werden
              daher dauerhaft aufbewahrt. Rechtsgrundlage für die Aufbewahrung über das Turnierende
              hinaus ist das berechtigte Interesse des Vereins an einer Vereinschronik gemäß Art. 6
              Abs. 1 lit. f DSGVO.
            </List.Item>
            <List.Item>
              <strong>Öffentliche Veröffentlichung:</strong> Das öffentlich zugängliche Dashboard
              eines Turniers wird automatisch deaktiviert, sobald das Turnier archiviert wird.
              Spielernamen und Ergebnisse sind danach im Internet nicht mehr öffentlich abrufbar.
            </List.Item>
            <List.Item>
              <strong>Server-Protokolldaten</strong> werden spätestens nach 30 Tagen gelöscht.
            </List.Item>
            <List.Item>
              <strong>Organisator-Konten</strong> bestehen, solange das Konto aktiv ist, und werden
              nach Deaktivierung innerhalb angemessener Frist gelöscht.
            </List.Item>
          </List>

          <Title order={3}>6. Deine Rechte</Title>
          <Text>
            Du hast nach der DSGVO folgende Rechte uns gegenüber: Auskunft (Art. 15), Berichtigung
            (Art. 16), Löschung (Art. 17), Einschränkung der Verarbeitung (Art. 18),
            Datenübertragbarkeit (Art. 20) und Widerspruch gegen Verarbeitungen, die auf einem
            berechtigten Interesse beruhen (Art. 21).
          </Text>
          <Text>
            Um diese Rechte auszuüben, genügt eine formlose Nachricht an{' '}
            <Anchor href="mailto:maud@aufschlag.org">maud@aufschlag.org</Anchor>. Wir antworten
            innerhalb der gesetzlichen Frist von einem Monat (Art. 12 Abs. 3 DSGVO; bei besonders
            komplexen Anfragen kann sich die Frist um bis zu zwei weitere Monate verlängern).
          </Text>

          <Title order={3}>7. Beschwerderecht</Title>
          <Text>
            Du hast das Recht, eine Beschwerde bei der zuständigen Aufsichtsbehörde einzureichen.
            Für Österreich ist das die Datenschutzbehörde:
          </Text>
          <Text>
            Österreichische Datenschutzbehörde
            <br />
            Barichgasse 40–42, 1030 Wien
            <br />
            <Anchor href="https://www.dsb.gv.at" target="_blank" rel="noreferrer">
              www.dsb.gv.at
            </Anchor>
          </Text>

          <Title order={3}>8. Datensicherheit</Title>
          <Text>
            Die Verbindung zur Website ist mit TLS verschlüsselt. Passwörter werden ausschließlich
            als kryptographischer Hash gespeichert. Der Zugriff auf den Server ist auf einen kleinen
            Personenkreis innerhalb des Vereins beschränkt.
          </Text>
        </Stack>
      </Stack>
    </Container>
  );
}
