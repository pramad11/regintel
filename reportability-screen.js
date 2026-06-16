/* ═══════════════════════════════════════════════════════════════════
   REGINTEL — REPORTABILITY DECISION TREE SCREEN
   Drop-in module for platform.html
   ─────────────────────────────────────────────────────────────────
   INTEGRATION (3 steps):

   1. NAV BUTTON — add to the sidebar nav <ul> in platform.html:
      <li onclick="showScreen('reportability')" data-screen="reportability">
        <i class="fas fa-sitemap"></i> Reportability
      </li>

   2. SCREEN CONTAINER — add to the main content area:
      <div id="screen-reportability" class="screen" style="display:none"></div>

   3. ROUTER — in your showScreen() function add:
      if(name === 'reportability') renderReportabilityScreen();

   4. CSS — paste the CSS block at bottom of <style> in platform.html.
   ─────────────────────────────────────────────────────────────────
   PATTERNS HONORED:
   - All HTML built via string concatenation (no template literals)
   - All apostrophes inside JS strings escaped as \u2019 or "you have"
   - Container ID: screen-reportability (not resultsScroll)
   ═══════════════════════════════════════════════════════════════════ */

const REP_SOURCES = [
  { id:'spontaneous', icon:'fa-user',            label:'Spontaneous',         sub:'Patient/HCP reports, consumer contacts' },
  { id:'literature',  icon:'fa-book',            label:'Literature',          sub:'Published case reports, journal articles' },
  { id:'clinical',    icon:'fa-flask',           label:'Clinical trial',      sub:'IND, Phase I-IV, investigational use' },
  { id:'premarket',   icon:'fa-microscope',      label:'Pre-market / EAP',    sub:'Expanded access, compassionate use' },
  { id:'postmarket',  icon:'fa-hospital',        label:'Post-market',         sub:'Approved products, registry, PMSS' },
  { id:'solicited',   icon:'fa-comments',        label:'Solicited programs',  sub:'Patient support, market research' },
  { id:'digital',     icon:'fa-mobile-alt',      label:'Digital / Social',    sub:'App, website, online community' },
  { id:'aggregate',   icon:'fa-chart-bar',       label:'Aggregate / Periodic',sub:'PSUR, PBRER, DSUR, PADER' }
];

const REP_HAS = [
  { id:'fda',        label:'FDA',         region:'United States'   },
  { id:'ema',        label:'EMA',         region:'European Union'  },
  { id:'mhra',       label:'MHRA',        region:'United Kingdom'  },
  { id:'hc',         label:'Health Canada', region:'Canada'        },
  { id:'tga',        label:'TGA',         region:'Australia'       },
  { id:'pmda',       label:'PMDA',        region:'Japan'           },
  { id:'mfds',       label:'MFDS',        region:'South Korea'     },
  { id:'sfda',       label:'SFDA',        region:'Saudi Arabia'    },
  { id:'swissmedic', label:'Swissmedic',  region:'Switzerland'     },
  { id:'anvisa',     label:'ANVISA',      region:'Brazil'          },
  { id:'cdsco',      label:'CDSCO',       region:'India'           },
  { id:'nmpa',       label:'NMPA',        region:'China'           },
  { id:'tfda',       label:'TFDA',        region:'Taiwan'          },
  { id:'moh',        label:'MOH',         region:'Israel'          },
  { id:'medsafe',    label:'Medsafe',     region:'New Zealand'     },
  { id:'nafdac',     label:'NAFDAC',      region:'Nigeria'         }
];

/* FLOWS data structure:
   step types: q=question, y=yes-branch, n=no-branch, i=info note
   each flow ends with an outcomes array (report/conditional/noreport)
   ──────────────────────────────────────────────────────────────── */
const REP_FLOWS = {
  spontaneous: {
    fda: [
      { t:'q', text:'<b>Is the product approved / marketed in the US?</b>' },
      { t:'y', text:'Yes \u2192 Subject to 21 CFR 314.80 (NDA/ANDA) or 21 CFR 600.80 (BLA)' },
      { t:'q', text:'<b>Is the AE serious?</b> (death, life-threatening, hospitalization, disability, congenital anomaly, medically important)' },
      { t:'y', text:'Yes &amp; unexpected \u2192 <b>15-day expedited</b> MedWatch 3500A to FDA' },
      { t:'y', text:'Yes &amp; expected (labeled) \u2192 <b>15-day</b> if fatal/LT; otherwise periodic' },
      { t:'n', text:'Non-serious \u2192 <b>PADER/periodic</b>; no expedited requirement' },
      { t:'i', text:'E2B R2 (MedWatch) or E2B R3 via FDA ESG. Reporter identity must be verified.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day expedited',     detail:'21 CFR 314.80(c)(1)(i)' },
        { cls:'out-conditional',title:'Serious expected (fatal/LT) \u2192 15-day',      detail:'21 CFR 314.80(c)(1)(ii)' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Periodic (PADER)',            detail:'21 CFR 314.80(c)(2)' }
      ]}
    ],
    ema: [
      { t:'q', text:'<b>Is product authorized in the EU (MA holder)?</b>' },
      { t:'y', text:'Yes \u2192 GVP Module VI Rev 2 \u00a7VI.B.6.1 applies' },
      { t:'q', text:'<b>Is the AE serious?</b>' },
      { t:'y', text:'Serious + unexpected \u2192 <b>15 calendar days</b> to EudraVigilance' },
      { t:'y', text:'Serious + expected \u2192 <b>15 days</b> if fatal/LT; <b>90 days</b> otherwise' },
      { t:'n', text:'Non-serious \u2192 <b>90 days</b> via EudraVigilance' },
      { t:'i', text:'E2B R3 mandatory since Nov 2017. EVWEB or gateway submission.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day EudraVigilance',  detail:'GVP Module VI \u00a7VI.B.6.1' },
        { cls:'out-conditional',title:'Serious expected \u2192 15-day (fatal/LT) or 90-day', detail:'\u00a7VI.B.6.2' },
        { cls:'out-noreport',   title:'Non-serious \u2192 90-day EudraVigilance',          detail:'\u00a7VI.B.6.3' }
      ]}
    ],
    mhra: [
      { t:'q', text:'<b>Is product authorized in UK (post-Brexit)?</b>' },
      { t:'y', text:'Yes \u2192 UK GVP Module VI applies' },
      { t:'q', text:'<b>AE serious?</b>' },
      { t:'y', text:'Serious + unexpected \u2192 <b>15 days</b> to MHRA Yellow Card' },
      { t:'y', text:'Serious + expected \u2192 <b>15 days</b> if fatal/LT; periodic otherwise' },
      { t:'n', text:'Non-serious \u2192 <b>90 days</b> Yellow Card' },
      { t:'i', text:'Yellow Card gateway (E2B R3). Separate from EU EudraVigilance post-Brexit.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day Yellow Card', detail:'UK GVP Module VI' },
        { cls:'out-conditional',title:'Serious expected \u2192 15-day or periodic',  detail:'UK MAH obligations' },
        { cls:'out-noreport',   title:'Non-serious \u2192 90-day Yellow Card',       detail:'UK post-Brexit' }
      ]}
    ],
    hc: [
      { t:'q', text:'<b>Is product marketed in Canada (NOC/NOC-c)?</b>' },
      { t:'y', text:'Yes \u2192 FDR C.01.016 &amp; MHPD guidance' },
      { t:'q', text:'<b>Is AE serious?</b>' },
      { t:'y', text:'Serious (domestic or foreign from Canadian MAH) \u2192 <b>15 days</b> via MedEffect' },
      { t:'n', text:'Non-serious \u2192 PSUR/annual; no expedited' },
      { t:'i', text:'E2B R2 currently; E2B R3 transition in progress. MedEffect portal.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious \u2192 15-day MedEffect',     detail:'FDR C.01.016' },
        { cls:'out-noreport',title:'Non-serious \u2192 Annual/PSUR only', detail:'MHPD Guidance' }
      ]}
    ],
    tga: [
      { t:'q', text:'<b>Is product registered on ARTG?</b>' },
      { t:'y', text:'Yes \u2192 TGA PV Responsibilities of Sponsors applies' },
      { t:'q', text:'<b>AE serious + unexpected?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 calendar days</b> to TGA eBS' },
      { t:'y', text:'Serious expected fatal/LT \u2192 <b>15 days</b>; PSUR otherwise' },
      { t:'n', text:'Non-serious \u2192 PSUR; no expedited' },
      { t:'i', text:'TGA accepts E2B R3. eBS portal mandatory for MAHs.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day eBS', detail:'TGA PV Responsibilities Guidance' },
        { cls:'out-conditional',title:'Serious expected fatal/LT \u2192 15-day', detail:'TGA guidance' },
        { cls:'out-noreport',   title:'Non-serious \u2192 PSUR', detail:'Periodic inclusion' }
      ]}
    ],
    pmda: [
      { t:'q', text:'<b>Is product approved in Japan?</b>' },
      { t:'y', text:'Yes \u2192 PAL / PFAS regulations apply' },
      { t:'q', text:'<b>Is AE serious?</b>' },
      { t:'y', text:'Serious unexpected (domestic or foreign) \u2192 <b>15 days</b> to PMDA' },
      { t:'y', text:'Serious expected domestic \u2192 <b>30 days</b>' },
      { t:'n', text:'Non-serious \u2192 Periodic only' },
      { t:'i', text:'PMDA accepts E2B R2/R3. Japanese narrative required.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day',          detail:'PFAS Art. 228-20' },
        { cls:'out-conditional',title:'Serious expected domestic \u2192 30-day',   detail:'PAL obligations' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Periodic',                detail:'PMDA guidance' }
      ]}
    ],
    mfds: [
      { t:'q', text:'<b>Is product approved in South Korea?</b>' },
      { t:'y', text:'Yes \u2192 KGVP regulations apply' },
      { t:'q', text:'<b>AE serious + unexpected?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> to MFDS DUR' },
      { t:'y', text:'Serious expected fatal \u2192 <b>15 days</b>; 30-day otherwise' },
      { t:'n', text:'Non-serious \u2192 PSUR; no expedited' },
      { t:'i', text:'E2B R2 currently. KFDA portal. Korean narrative preferred.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day MFDS',    detail:'KGVP regulations' },
        { cls:'out-conditional',title:'Serious expected \u2192 15-30 day',         detail:'KGVP, severity-dependent' },
        { cls:'out-noreport',   title:'Non-serious \u2192 PSUR',                   detail:'Periodic reporting' }
      ]}
    ],
    sfda: [
      { t:'q', text:'<b>Is product registered in Saudi Arabia?</b>' },
      { t:'y', text:'Yes \u2192 Saudi GVP Module VI applies' },
      { t:'q', text:'<b>AE serious + unexpected?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> to SFDA PV portal' },
      { t:'y', text:'Serious expected fatal/LT \u2192 <b>15 days</b>; 30-day otherwise' },
      { t:'n', text:'Non-serious \u2192 Annual PSUR; no expedited' },
      { t:'i', text:'SFDA PV Online portal. E2B-compatible. English accepted.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day SFDA',  detail:'Saudi GVP Module VI' },
        { cls:'out-conditional',title:'Serious expected \u2192 15-30 day',       detail:'Severity-based' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Annual PSUR',          detail:'SFDA guidance' }
      ]}
    ],
    swissmedic: [
      { t:'q', text:'<b>Is product authorized by Swissmedic?</b>' },
      { t:'y', text:'Yes \u2192 Swiss HMG &amp; Swissmedic GVP guidance' },
      { t:'q', text:'<b>AE serious + unexpected?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> to Swissmedic portal' },
      { t:'y', text:'Serious expected fatal/LT \u2192 <b>15 days</b>; <b>90 days</b> otherwise' },
      { t:'n', text:'Non-serious \u2192 <b>90 days</b> electronic submission' },
      { t:'i', text:'Aligns with EMA GVP post-MRA. E2B R3 accepted. Separate from EudraVigilance.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day Swissmedic',  detail:'Swiss HMG / GVP' },
        { cls:'out-conditional',title:'Serious expected \u2192 15-day (fatal) or 90-day', detail:'Swissmedic guidance' },
        { cls:'out-noreport',   title:'Non-serious \u2192 90-day',                     detail:'Electronic portal' }
      ]}
    ],
    anvisa: [
      { t:'q', text:'<b>Is product registered with ANVISA?</b>' },
      { t:'y', text:'Yes \u2192 RDC 204/2017 applies' },
      { t:'q', text:'<b>Is AE serious?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> via Notivisa' },
      { t:'y', text:'Serious expected fatal \u2192 <b>15 days</b>; <b>30 days</b> otherwise' },
      { t:'n', text:'Non-serious \u2192 <b>90 days</b> periodic' },
      { t:'i', text:'Notivisa portal. Portuguese narrative required.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day Notivisa', detail:'RDC 204/2017' },
        { cls:'out-conditional',title:'Serious expected \u2192 15-30 day',          detail:'Severity-dependent' },
        { cls:'out-noreport',   title:'Non-serious \u2192 90-day periodic',         detail:'Annual report' }
      ]}
    ],
    cdsco: [
      { t:'q', text:'<b>Is product licensed in India (Form 27/28)?</b>' },
      { t:'y', text:'Yes \u2192 Schedule Y &amp; PvPI Guidance apply' },
      { t:'q', text:'<b>Is AE serious?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> to CDSCO/PvPI via Vigiflow' },
      { t:'y', text:'Serious expected fatal \u2192 <b>15 days</b>; periodic otherwise' },
      { t:'n', text:'Non-serious \u2192 Annual safety report; no expedited' },
      { t:'i', text:'PvPI (Pharmacovigilance Programme of India). Vigiflow gateway.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day CDSCO/PvPI', detail:'Schedule Y / PvPI Guidance' },
        { cls:'out-conditional',title:'Serious expected fatal \u2192 15-day',         detail:'PvPI requirements' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Annual safety report',     detail:'Schedule Y' }
      ]}
    ],
    nmpa: [
      { t:'q', text:'<b>Is product registered with NMPA?</b>' },
      { t:'y', text:'Yes \u2192 ADR Reporting Measures 2011/2022 apply' },
      { t:'q', text:'<b>Is AE new/serious?</b>' },
      { t:'y', text:'Serious (any) \u2192 <b>15 days</b> via CNKI ADR system' },
      { t:'y', text:'Non-serious \u2192 <b>30 days</b> via CNKI (all ADRs reportable)' },
      { t:'i', text:'No "expected = no report" rule. Chinese language narrative required.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious (any) \u2192 15-day CNKI',          detail:'China ADR Measures 2011/2022' },
        { cls:'out-report',  title:'Non-serious \u2192 30-day CNKI',            detail:'All ADRs must be reported' },
        { cls:'out-noreport',title:'All serious ADRs reportable',               detail:'No expected exclusion in China' }
      ]}
    ],
    tfda: [
      { t:'q', text:'<b>Is product licensed in Taiwan?</b>' },
      { t:'y', text:'Yes \u2192 TFDA Drug Injury Relief Fund Act &amp; ADR regulations' },
      { t:'q', text:'<b>AE serious + unexpected?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> to TFDA portal' },
      { t:'y', text:'Serious expected fatal \u2192 <b>15 days</b>; 30 days otherwise' },
      { t:'n', text:'Non-serious \u2192 Annual report; no expedited' },
      { t:'i', text:'TFDA ADR online portal. Traditional Chinese preferred.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day TFDA', detail:'TFDA ADR regulations' },
        { cls:'out-conditional',title:'Serious expected \u2192 15-30 day',      detail:'Severity-dependent' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Annual',              detail:'Periodic submission' }
      ]}
    ],
    moh: [
      { t:'q', text:'<b>Is product registered by Israel MOH?</b>' },
      { t:'y', text:'Yes \u2192 Israel MOH PV guidelines (ICH E2A-aligned) apply' },
      { t:'q', text:'<b>AE serious + unexpected?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> to MOH PV department' },
      { t:'y', text:'Serious expected fatal/LT \u2192 <b>15 days</b>; 90-day otherwise' },
      { t:'n', text:'Non-serious \u2192 PSUR; no expedited' },
      { t:'i', text:'MOH PV portal. English and Hebrew accepted. ICH E2B format.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day MOH',     detail:'Israel MOH GVP' },
        { cls:'out-conditional',title:'Serious expected fatal/LT \u2192 15-day',   detail:'MOH PV guidance' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Periodic/PSUR',          detail:'Annual submission' }
      ]}
    ],
    medsafe: [
      { t:'q', text:'<b>Is product consented by Medsafe?</b>' },
      { t:'y', text:'Yes \u2192 Medicines Act 1981 &amp; Medsafe PV guidelines' },
      { t:'q', text:'<b>AE serious + unexpected?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> to Medsafe portal' },
      { t:'y', text:'Serious expected fatal/LT \u2192 15-day; periodic otherwise' },
      { t:'n', text:'Non-serious \u2192 PSUR; no expedited' },
      { t:'i', text:'Aligned with TGA (trans-Tasman). English.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day Medsafe',  detail:'Medicines Act 1981' },
        { cls:'out-conditional',title:'Serious expected fatal/LT \u2192 15-day',    detail:'Medsafe PV guidelines' },
        { cls:'out-noreport',   title:'Non-serious \u2192 PSUR',                    detail:'Annual report' }
      ]}
    ],
    nafdac: [
      { t:'q', text:'<b>Is product registered with NAFDAC?</b>' },
      { t:'y', text:'Yes \u2192 NAFDAC PV regulations apply' },
      { t:'q', text:'<b>Is AE serious?</b>' },
      { t:'y', text:'Serious \u2192 <b>15 days</b> to NAFDAC PV directorate' },
      { t:'n', text:'Non-serious \u2192 <b>90 days</b> periodic submission' },
      { t:'i', text:'NAFDAC ePV portal. English. E2B-compatible.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious \u2192 15-day NAFDAC',          detail:'NAFDAC PV Regulations' },
        { cls:'out-noreport',title:'Non-serious \u2192 90-day periodic',     detail:'NAFDAC guidance' }
      ]}
    ]
  },
  clinical: {
    fda: [
      { t:'q', text:'<b>Is this a US IND trial?</b>' },
      { t:'y', text:'Yes \u2192 21 CFR 312.32 (IND safety reporting) applies' },
      { t:'q', text:'<b>SAE unexpected (not in IB) and possibly related?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> IND Safety Report' },
      { t:'y', text:'SUSAR other serious \u2192 <b>15 days</b>' },
      { t:'y', text:'Expected serious \u2192 Annual IND Safety Report' },
      { t:'n', text:'Non-serious \u2192 CRF capture; annual aggregate' },
      { t:'i', text:'MedWatch 3500A or E2B R3 via FDA ESG. IND number required.' },
      { outcomes:[
        { cls:'out-report',     title:'SUSAR fatal/LT \u2192 7-day IND Safety Report', detail:'21 CFR 312.32(c)(2)' },
        { cls:'out-report',     title:'SUSAR other serious \u2192 15-day',              detail:'21 CFR 312.32(c)(1)' },
        { cls:'out-conditional',title:'Expected serious \u2192 Annual IND report',      detail:'21 CFR 312.33' },
        { cls:'out-noreport',   title:'Non-serious \u2192 CRF only',                    detail:'No expedited reporting' }
      ]}
    ],
    ema: [
      { t:'q', text:'<b>Trial under CTR 536/2014 or old Directive?</b>' },
      { t:'y', text:'CTR 536/2014 \u2192 CTIS portal (mandatory by Jan 2025)' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to all MSAs via CTIS' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b> to EVCTM (EudraVigilance)' },
      { t:'n', text:'Non-SUSAR SAE \u2192 Annual DSUR; no expedited' },
      { t:'i', text:'CTR 536/2014 Art. 42/43. E2B R3 format. All SUSARs to EVCTM.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day all MSAs',    detail:'CTR 536/2014 Art. 42' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day EVCTM',     detail:'CTR 536/2014 Art. 43' },
        { cls:'out-noreport',title:'Non-SUSAR SAE \u2192 DSUR only',          detail:'Annual aggregate' }
      ]}
    ],
    mhra: [
      { t:'q', text:'<b>Trial authorized under UK CTA?</b>' },
      { t:'y', text:'Yes \u2192 Medicines for Human Use (CT) Regs 2004' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to MHRA + investigators + ethics' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b> to MHRA + investigators' },
      { t:'n', text:'Non-SUSAR SAE \u2192 DSUR; no expedited' },
      { t:'i', text:'MHRA CT portal (post-Brexit). E2B R3.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day MHRA + invest.', detail:'CT Regs 2004, Reg 33' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day MHRA',          detail:'CT Regs 2004, Reg 34' },
        { cls:'out-noreport',title:'Non-SUSAR \u2192 DSUR annual',                detail:'CT Regs 2004' }
      ]}
    ],
    hc: [
      { t:'q', text:'<b>Trial under Canadian CTA?</b>' },
      { t:'y', text:'Yes \u2192 FDR Division 5 applies' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to Health Canada' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b> via eSubmission' },
      { t:'n', text:'Non-SUSAR \u2192 Annual Progress/Safety Report' },
      { t:'i', text:'Health Canada eSubmission portal. E2B R2 currently.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day',         detail:'FDR Division 5' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day',       detail:'FDR Division 5' },
        { cls:'out-noreport',title:'Non-SUSAR \u2192 Annual Progress',    detail:'FDR C.05.012' }
      ]}
    ],
    tga: [
      { t:'q', text:'<b>Trial under Australian CTN or CTA?</b>' },
      { t:'y', text:'Yes \u2192 TGA SUSAR reporting obligations apply' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to TGA + HREC' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b> via eBS portal' },
      { t:'n', text:'Non-SUSAR \u2192 DSUR' },
      { t:'i', text:'TGA eBS portal. HREC notification also required.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day TGA + HREC', detail:'TGA CT guidelines' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day eBS',       detail:'TGA guidance' },
        { cls:'out-noreport',title:'Non-SUSAR \u2192 DSUR',                   detail:'Annual safety' }
      ]}
    ],
    pmda: [
      { t:'q', text:'<b>Trial under PMDA approval / ICH E6?</b>' },
      { t:'y', text:'Yes \u2192 PFAS + Ministerial Ordinance 36A' },
      { t:'q', text:'<b>SAE unexpected and related?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to PMDA + MHLW' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b>' },
      { t:'y', text:'Expected serious domestic \u2192 <b>30 days</b>; 15-day if foreign' },
      { t:'n', text:'Non-serious \u2192 DSUR' },
      { t:'i', text:'PMDA gateway. Japanese narrative required.' },
      { outcomes:[
        { cls:'out-report',     title:'SUSAR fatal/LT \u2192 7-day',                detail:'PAL / Ord. 36A' },
        { cls:'out-report',     title:'SUSAR non-fatal \u2192 15-day',              detail:'PFAS regulations' },
        { cls:'out-conditional',title:'Expected serious \u2192 30-day / 15-day',     detail:'PMDA guidance' },
        { cls:'out-noreport',   title:'Non-serious \u2192 DSUR',                    detail:'Aggregate only' }
      ]}
    ],
    mfds: [
      { t:'q', text:'<b>Trial in South Korea under MFDS IND?</b>' },
      { t:'y', text:'Yes \u2192 KGVP CT provisions apply' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to MFDS' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b>' },
      { t:'n', text:'Non-SUSAR \u2192 Annual safety report' },
      { t:'i', text:'MFDS KGVP CT portal. Korean narrative preferred.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day MFDS',  detail:'KGVP CT provisions' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day',     detail:'KGVP regulations' },
        { cls:'out-noreport',title:'Non-SUSAR \u2192 Annual',           detail:'Periodic only' }
      ]}
    ],
    sfda: [
      { t:'q', text:'<b>Trial under SFDA IND in Saudi Arabia?</b>' },
      { t:'y', text:'Yes \u2192 Saudi GVP CT provisions apply' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to SFDA + IRB' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b> to SFDA' },
      { t:'n', text:'Non-SUSAR \u2192 Periodic' },
      { t:'i', text:'SFDA PV portal. English accepted.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day SFDA + IRB', detail:'Saudi GVP CT' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day SFDA',     detail:'Saudi GVP CT' },
        { cls:'out-noreport',title:'Non-SUSAR \u2192 Periodic',              detail:'Annual safety report' }
      ]}
    ],
    swissmedic: [
      { t:'q', text:'<b>Trial under Swiss CTA (Swissmedic)?</b>' },
      { t:'y', text:'Yes \u2192 Swiss HRA &amp; Swissmedic CT SUSAR reporting' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to Swissmedic + Cantonal Ethics' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b>' },
      { t:'n', text:'Non-SUSAR \u2192 DSUR' },
      { t:'i', text:'Swissmedic CT portal. ICH E6(R2)-aligned.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day Swissmedic + Ethics', detail:'Swiss HRA / CT' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day',                    detail:'Swiss CT regulations' },
        { cls:'out-noreport',title:'Non-SUSAR \u2192 DSUR annual',                     detail:'Annual report' }
      ]}
    ],
    anvisa: [
      { t:'q', text:'<b>Trial approved by ANVISA + CONEP?</b>' },
      { t:'y', text:'Yes \u2192 RDC 9/2015 + ANVISA CT SUSAR obligations' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to ANVISA + CONEP' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b> via Notivisa' },
      { t:'n', text:'Non-SUSAR \u2192 Periodic safety report' },
      { t:'i', text:'ANVISA Notivisa portal. Portuguese required.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day ANVISA + CONEP', detail:'RDC 9/2015' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day Notivisa',      detail:'ANVISA CT regulations' },
        { cls:'out-noreport',title:'Non-SUSAR \u2192 Periodic',                   detail:'Annual safety' }
      ]}
    ],
    cdsco: [
      { t:'q', text:'<b>Trial under CDSCO IND in India?</b>' },
      { t:'y', text:'Yes \u2192 Schedule Y + ND&amp;CT Rules 2019 apply' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>14 days</b> to CDSCO + IEC' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>30 days</b>' },
      { t:'n', text:'Non-SUSAR SAE \u2192 IEC 14-day + CDSCO annual' },
      { t:'i', text:'CDSCO Sugam portal. ND&amp;CT Rules 2019 — non-ICH timelines.' },
      { outcomes:[
        { cls:'out-report',     title:'SUSAR fatal/LT \u2192 14-day CDSCO + IEC', detail:'ND&CT Rules 2019' },
        { cls:'out-report',     title:'SUSAR non-fatal \u2192 30-day CDSCO',      detail:'ND&CT Rules 2019' },
        { cls:'out-conditional',title:'Non-SUSAR SAE \u2192 IEC 14-day',           detail:'SAE management' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Annual',                  detail:'Periodic' }
      ]}
    ],
    nmpa: [
      { t:'q', text:'<b>Trial approved by NMPA in China?</b>' },
      { t:'y', text:'Yes \u2192 NMPA IND CT safety reporting applies' },
      { t:'q', text:'<b>SAE unexpected and related?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to NMPA' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b>' },
      { t:'y', text:'All domestic SAEs \u2192 <b>15 days</b> (no expected exception)' },
      { t:'n', text:'Non-serious \u2192 Annual aggregate' },
      { t:'i', text:'NMPA eCTD portal. Chinese narrative required.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day NMPA',  detail:'NMPA CT regulations' },
        { cls:'out-report',  title:'All domestic SAEs \u2192 15-day',    detail:'No expected exception' },
        { cls:'out-noreport',title:'Non-serious \u2192 Annual',          detail:'Aggregate' }
      ]}
    ],
    tfda: [
      { t:'q', text:'<b>Trial under TFDA IND (Taiwan)?</b>' },
      { t:'y', text:'Yes \u2192 TFDA CT safety reporting applies' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to TFDA + IRB' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b> to TFDA' },
      { t:'n', text:'Non-SUSAR \u2192 DSUR' },
      { t:'i', text:'TFDA eCTD portal. ICH E6(R2)-aligned.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day TFDA + IRB', detail:'TFDA CT regulations' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day',           detail:'TFDA guidance' },
        { cls:'out-noreport',title:'Non-SUSAR \u2192 DSUR',                   detail:'Annual only' }
      ]}
    ],
    moh: [
      { t:'q', text:'<b>Trial approved by Israel MOH + Helsinki Committee?</b>' },
      { t:'y', text:'Yes \u2192 Israel MOH CT regulations (ICH GCP-aligned) apply' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to MOH + Helsinki Committee' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b> to MOH' },
      { t:'n', text:'Non-SUSAR \u2192 DSUR annual; no expedited' },
      { t:'i', text:'Israel MOH portal. English/Hebrew. ICH E6(R2).' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day MOH + Helsinki', detail:'Israel MOH CT regulations' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day MOH',           detail:'MOH CT guidance' },
        { cls:'out-noreport',title:'Non-SUSAR \u2192 DSUR annual',                detail:'Annual report' }
      ]}
    ],
    medsafe: [
      { t:'q', text:'<b>Trial approved by Medsafe + HDEC?</b>' },
      { t:'y', text:'Yes \u2192 Medsafe CT SUSAR obligations (TGA-aligned)' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> to Medsafe + HDEC' },
      { t:'y', text:'SUSAR non-fatal \u2192 <b>15 days</b> to Medsafe' },
      { t:'n', text:'Non-SUSAR \u2192 DSUR' },
      { t:'i', text:'Medsafe portal. Trans-Tasman alignment with TGA.' },
      { outcomes:[
        { cls:'out-report',  title:'SUSAR fatal/LT \u2192 7-day Medsafe + HDEC', detail:'Medicines Act 1981' },
        { cls:'out-report',  title:'SUSAR non-fatal \u2192 15-day Medsafe',       detail:'Medsafe CT guidance' },
        { cls:'out-noreport',title:'Non-SUSAR \u2192 DSUR annual',                detail:'Annual safety' }
      ]}
    ],
    nafdac: [
      { t:'q', text:'<b>Trial authorized by NAFDAC in Nigeria?</b>' },
      { t:'y', text:'Yes \u2192 NAFDAC CT regulations + NHREC apply' },
      { t:'q', text:'<b>Is SAE a SUSAR?</b>' },
      { t:'y', text:'SUSAR \u2192 <b>7-15 days</b> to NAFDAC + NHREC' },
      { t:'n', text:'Non-SUSAR SAE \u2192 Periodic + NHREC notify' },
      { t:'i', text:'NAFDAC CT portal. English. WHO GCP-aligned.' },
      { outcomes:[
        { cls:'out-report',     title:'SUSAR \u2192 7-15 day NAFDAC + NHREC',  detail:'NAFDAC CT regulations' },
        { cls:'out-conditional',title:'Non-SUSAR SAE \u2192 NHREC + periodic',  detail:'NAFDAC CT guidance' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Annual aggregate',    detail:'Periodic report' }
      ]}
    ]
  },
  literature:  buildLiteratureFlows(),
  premarket:   buildPremarketFlows(),
  postmarket:  buildPostmarketFlows(),
  solicited:   buildSolicitedFlows(),
  digital:     buildDigitalFlows(),
  aggregate:   buildAggregateFlows()
};

/* ─── Compact builders for remaining sources ──────────────────────
   Each function returns the per-HA flows for that source.
   Pattern keeps platform.html under reasonable size.
   ───────────────────────────────────────────────────────────────── */

function buildLiteratureFlows() {
  // Standard literature pattern: monitoring obligation, 4 criteria check, then severity-based timing
  return {
    fda: [
      { t:'q', text:'<b>Article references your marketed product?</b>' },
      { t:'y', text:'Yes \u2192 21 CFR 314.81(b) + FDA literature screening guidance' },
      { t:'q', text:'<b>4 minimum criteria met?</b> (patient, reporter, product, AE)' },
      { t:'y', text:'Yes + serious + unexpected \u2192 <b>15 days</b> MedWatch' },
      { t:'y', text:'Yes + non-serious / expected \u2192 PADER' },
      { t:'n', text:'< 4 criteria \u2192 Document; no ICSR' },
      { t:'i', text:'Screen WHO core journals + 50+ MAH list. Awareness = article identification date.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected (4 criteria) \u2192 15-day', detail:'21 CFR 314.81(b)' },
        { cls:'out-conditional',title:'Non-serious / expected \u2192 PADER',           detail:'Periodic' },
        { cls:'out-noreport',   title:'< 4 criteria \u2192 Screening log only',         detail:'Document' }
      ]}
    ],
    ema: [
      { t:'q', text:'<b>Article from journal MAH must screen?</b>' },
      { t:'y', text:'Yes \u2192 GVP Module VI \u00a7VI.B.2.1.5 (WHO core journals)' },
      { t:'q', text:'<b>4 minimum ICSR criteria met?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> EudraVigilance' },
      { t:'y', text:'Non-serious \u2192 <b>90 days</b> EudraVigilance' },
      { t:'n', text:'< 4 criteria \u2192 Document; no ICSR' },
      { t:'i', text:'Awareness = receipt date by sponsor. E2B R3 EVWEB.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day EudraVigilance', detail:'GVP Module VI \u00a7VI.B.2.1.5' },
        { cls:'out-conditional',title:'Non-serious \u2192 90-day',                       detail:'GVP Module VI' },
        { cls:'out-noreport',   title:'< 4 criteria \u2192 Screening log',                detail:'Documentation required' }
      ]}
    ],
    mhra: stdLiteratureFlow('UK GVP Module VI', 'MHRA Yellow Card', 'UK SmPC reference (post-Brexit)'),
    hc:   stdLiteratureFlow('FDR C.01.016 / MHPD guidance', 'Health Canada MedEffect', 'WHO core journals'),
    tga:  stdLiteratureFlow('TGA PV Responsibilities Guidance', 'TGA eBS portal', 'WHO core + Australian journals'),
    pmda: [
      { t:'q', text:'<b>Article references Japan-approved product?</b>' },
      { t:'y', text:'Yes \u2192 PFAS literature monitoring applies' },
      { t:'q', text:'<b>4 criteria + serious + unexpected?</b>' },
      { t:'y', text:'Domestic or foreign lit. \u2192 <b>15 days</b> to PMDA' },
      { t:'n', text:'Non-serious \u2192 Periodic' },
      { t:'i', text:'Japanese narrative for domestic lit. cases. Both domestic + international screening.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious unexpected \u2192 15-day PMDA',  detail:'PFAS literature obligations' },
        { cls:'out-noreport',title:'Non-serious / < 4 criteria \u2192 Periodic', detail:'Annual aggregate' }
      ]}
    ],
    mfds:       stdLiteratureFlow('KGVP literature obligations', 'MFDS', 'Korean + international journals'),
    sfda:       stdLiteratureFlow('Saudi GVP Module VI', 'SFDA PV portal', 'International + Arabic literature'),
    swissmedic: stdLiteratureFlow('Swiss HMG / GVP', 'Swissmedic portal', 'WHO core journals', true),
    anvisa:     stdLiteratureFlow('RDC 204/2017', 'ANVISA Notivisa', 'Portuguese for reports'),
    cdsco:      stdLiteratureFlow('Schedule Y / PvPI lit. guidance', 'CDSCO/PvPI Vigiflow', 'English'),
    nmpa: [
      { t:'q', text:'<b>Article references NMPA-registered product?</b>' },
      { t:'y', text:'Yes \u2192 China ADR Measures: all ADRs from lit. must be reported' },
      { t:'q', text:'<b>4 criteria met?</b>' },
      { t:'y', text:'Serious \u2192 <b>15 days</b> CNKI' },
      { t:'y', text:'Non-serious \u2192 <b>30 days</b> CNKI' },
      { t:'n', text:'< 4 criteria \u2192 Document' },
      { t:'i', text:'Chinese + international journals. All ADRs reportable.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious \u2192 15-day CNKI',     detail:'China ADR Measures' },
        { cls:'out-report',  title:'Non-serious \u2192 30-day CNKI',  detail:'All ADRs reportable' },
        { cls:'out-noreport',title:'< 4 criteria \u2192 Log only',     detail:'Document' }
      ]}
    ],
    tfda:    stdLiteratureFlow('TFDA ADR regulations', 'TFDA', 'Traditional Chinese preferred'),
    moh:     stdLiteratureFlow('Israel MOH GVP guidelines', 'MOH PV department', 'English/Hebrew'),
    medsafe: stdLiteratureFlow('Medicines Act / Medsafe guidance', 'Medsafe', 'NZ + international journals'),
    nafdac:  stdLiteratureFlow('NAFDAC PV regulations', 'NAFDAC PV directorate', 'Nigerian + international')
  };
}

function stdLiteratureFlow(framework, portal, detail, withNonSerious) {
  const flow = [
    { t:'q', text:'<b>Article references product registered in this jurisdiction?</b>' },
    { t:'y', text:'Yes \u2192 ' + framework + ' applies' },
    { t:'q', text:'<b>4 minimum criteria + serious + unexpected?</b>' },
    { t:'y', text:'Yes \u2192 <b>15 days</b> to ' + portal }
  ];
  if (withNonSerious) flow.push({ t:'y', text:'Non-serious \u2192 <b>90 days</b> ' + portal });
  flow.push({ t:'n', text:'< 4 criteria or non-serious \u2192 Annual PSUR' });
  flow.push({ t:'i', text:detail });
  const outcomes = [
    { cls:'out-report', title:'Serious unexpected \u2192 15-day ' + portal, detail:framework }
  ];
  if (withNonSerious) outcomes.push({ cls:'out-conditional', title:'Non-serious \u2192 90-day', detail:'Periodic lit. case' });
  outcomes.push({ cls:'out-noreport', title:'< 4 criteria / non-serious \u2192 PSUR', detail:'Annual' });
  flow.push({ outcomes:outcomes });
  return flow;
}

function buildPremarketFlows() {
  return {
    fda: [
      { t:'q', text:'<b>Is this an Expanded Access IND or Named Patient Program?</b>' },
      { t:'y', text:'Yes \u2192 21 CFR 312.310 + 312.32 apply' },
      { t:'q', text:'<b>Is SAE serious, unexpected, and possibly related?</b>' },
      { t:'y', text:'SUSAR fatal/LT \u2192 <b>7 days</b> (IND Safety Report)' },
      { t:'y', text:'SUSAR other serious \u2192 <b>15 days</b>' },
      { t:'y', text:'Expected SAE \u2192 IND annual update' },
      { t:'n', text:'Non-serious \u2192 Annual aggregate' },
      { t:'i', text:'Expanded Access IND number required. Same obligations as Phase II/III IND.' },
      { outcomes:[
        { cls:'out-report',     title:'SUSAR fatal/LT \u2192 7-day FDA',   detail:'21 CFR 312.32(c)(2)' },
        { cls:'out-report',     title:'SUSAR serious \u2192 15-day FDA',    detail:'21 CFR 312.32(c)(1)' },
        { cls:'out-conditional',title:'Expected SAE \u2192 IND annual',      detail:'21 CFR 312.33' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Annual aggregate', detail:'No expedited' }
      ]}
    ],
    ema: [
      { t:'q', text:'<b>EU Named Patient Program or Compassionate Use?</b>' },
      { t:'y', text:'Yes \u2192 Reg 726/2004 Art. 83 + MS national laws' },
      { t:'q', text:'<b>Linked to authorized CTA?</b>' },
      { t:'y', text:'CTA-linked \u2192 SUSAR rules (CTR 536/2014)' },
      { t:'y', text:'Standalone NPP \u2192 Report to each MS national CA' },
      { t:'q', text:'<b>Serious + unexpected?</b>' },
      { t:'y', text:'Yes \u2192 <b>15 days</b> to participating MS CAs' },
      { t:'n', text:'Non-serious \u2192 Periodic aggregate' },
      { t:'i', text:'No EU-wide harmonized NPP reporting. National variation.' },
      { outcomes:[
        { cls:'out-report',     title:'CTA-linked SUSAR \u2192 7/15-day all MSAs', detail:'CTR 536/2014' },
        { cls:'out-conditional',title:'NPP serious \u2192 15-day per MS CA',        detail:'Reg 726/2004 Art. 83' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Periodic',                detail:'Aggregate reporting' }
      ]}
    ],
    mhra:       stdPremarketFlow('UK Specials/NPP \u2192 UK Medicines Regs 2012', 'MHRA Yellow Card'),
    hc:         stdPremarketFlow('Health Canada SAP (C.08.010/011)', 'Health Canada SAP directorate'),
    tga:        stdPremarketFlow('TGA SAS \u2192 TG Act s.19', 'TGA eBS portal'),
    pmda:       stdPremarketFlow('Japan Sakigake / conditional approval', 'PMDA + MHLW'),
    mfds:       stdPremarketFlow('Korea KGVP early access provisions', 'MFDS DUR portal'),
    sfda:       stdPremarketFlow('SFDA Exceptional Access Program', 'SFDA PV portal'),
    swissmedic: stdPremarketFlow('Swiss HMG Art. 9c compassionate use', 'Swissmedic portal'),
    anvisa:     stdPremarketFlow('ANVISA EAP \u2192 RDC 204/2017', 'ANVISA Notivisa'),
    cdsco: [
      { t:'q', text:'<b>India Named Patient / Compassionate Use under CDSCO?</b>' },
      { t:'y', text:'Yes \u2192 ND&amp;CT Rules 2019 compassionate use apply' },
      { t:'q', text:'<b>Serious + unexpected?</b>' },
      { t:'y', text:'Yes \u2192 <b>14 days</b> to CDSCO + IEC' },
      { t:'n', text:'Non-serious \u2192 Annual; no expedited' },
      { t:'i', text:'CDSCO Sugam. Section 107A Drugs & Cosmetics Act. English.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious unexpected \u2192 14-day CDSCO',   detail:'ND&CT Rules 2019' },
        { cls:'out-noreport',title:'Non-serious \u2192 Annual',                detail:'Periodic' }
      ]}
    ],
    nmpa: [
      { t:'q', text:'<b>China emergency/conditional access under NMPA?</b>' },
      { t:'y', text:'Yes \u2192 NMPA conditional approval / EUA PV obligations' },
      { t:'q', text:'<b>Is SAE serious?</b>' },
      { t:'y', text:'Serious \u2192 <b>15 days</b> CNKI' },
      { t:'y', text:'Non-serious \u2192 <b>30 days</b> CNKI' },
      { t:'i', text:'No "expected" exception. Chinese narrative. All SAEs from emergency use reportable.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious \u2192 15-day CNKI',    detail:'NMPA ADR Measures' },
        { cls:'out-report',  title:'Non-serious \u2192 30-day CNKI', detail:'All ADRs reportable' },
        { cls:'out-noreport',title:'< 4 criteria \u2192 Document',    detail:'Screening log' }
      ]}
    ],
    tfda:    stdPremarketFlow('TFDA special access PV', 'TFDA portal'),
    moh:     stdPremarketFlow('Israel MOH "Tovlanot" special access', 'MOH PV department'),
    medsafe: stdPremarketFlow('Medsafe Provisional Consent / Unapproved Meds', 'Medsafe portal'),
    nafdac: [
      { t:'q', text:'<b>NAFDAC compassionate / EUA program?</b>' },
      { t:'y', text:'Yes \u2192 NAFDAC EUA PV obligations' },
      { t:'q', text:'<b>Is SAE serious?</b>' },
      { t:'y', text:'Serious \u2192 <b>15 days</b> NAFDAC + NHREC' },
      { t:'n', text:'Non-serious \u2192 Periodic' },
      { t:'i', text:'Nigeria EUA process. NHREC ethics oversight. English.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious \u2192 15-day NAFDAC + NHREC', detail:'NAFDAC EUA PV' },
        { cls:'out-noreport',title:'Non-serious \u2192 Periodic',           detail:'Annual report' }
      ]}
    ]
  };
}

function stdPremarketFlow(framework, portal) {
  return [
    { t:'q', text:'<b>Compassionate use / named patient program in this jurisdiction?</b>' },
    { t:'y', text:'Yes \u2192 ' + framework + ' applies' },
    { t:'q', text:'<b>Is SAE serious + unexpected?</b>' },
    { t:'y', text:'Yes \u2192 <b>15 days</b> to ' + portal },
    { t:'n', text:'Non-serious \u2192 Annual/periodic; no expedited' },
    { t:'i', text:'Standard EAP/compassionate use PV requirements apply per jurisdiction.' },
    { outcomes:[
      { cls:'out-report',  title:'Serious unexpected \u2192 15-day ' + portal, detail:framework },
      { cls:'out-noreport',title:'Non-serious \u2192 Annual',                    detail:'Periodic' }
    ]}
  ];
}

function buildPostmarketFlows() {
  return {
    fda: [
      { t:'q', text:'<b>Is this from a PMSS, registry, or REMS study?</b>' },
      { t:'y', text:'Yes \u2192 21 CFR 314.80 / 600.80 governs' },
      { t:'q', text:'<b>Is SAE serious + unexpected?</b>' },
      { t:'y', text:'Yes \u2192 <b>15 days</b> expedited MedWatch' },
      { t:'y', text:'Serious expected \u2192 PADER' },
      { t:'n', text:'Non-serious \u2192 PADER' },
      { t:'i', text:'REMS studies have additional commitments. 21 CFR 314.81.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected (PMSS/registry) \u2192 15-day', detail:'21 CFR 314.80(c)(1)' },
        { cls:'out-conditional',title:'Serious expected \u2192 PADER',                     detail:'21 CFR 314.81(b)(2)' },
        { cls:'out-noreport',   title:'Non-serious \u2192 PADER',                          detail:'Periodic aggregate' }
      ]}
    ],
    ema: [
      { t:'q', text:'<b>From a PASS (interventional or non-interventional)?</b>' },
      { t:'y', text:'Yes \u2192 GVP Module VI + Module VIII (PASS) apply' },
      { t:'q', text:'<b>Is SAE serious + unexpected?</b>' },
      { t:'y', text:'PASS serious unexpected \u2192 <b>15 days</b> EudraVigilance' },
      { t:'y', text:'Non-serious \u2192 <b>90 days</b> EudraVigilance' },
      { t:'i', text:'Protocol must be registered in EU PAS Register. PRAC oversight.' },
      { outcomes:[
        { cls:'out-report',     title:'PASS serious unexpected \u2192 15-day', detail:'GVP Module VI + VIII' },
        { cls:'out-conditional',title:'NIPASS \u2192 causality assessment',     detail:'GVP Module VI criteria' },
        { cls:'out-noreport',   title:'Non-serious \u2192 90-day',              detail:'GVP \u00a7VI.B.6.3' }
      ]}
    ],
    mhra:       stdPostmarketFlow('UK GVP Module VI/VIII (UK PASS)', 'MHRA Yellow Card', true),
    hc:         stdPostmarketFlow('FDR C.01.016 / MHPD CMA commitments', 'Health Canada MedEffect'),
    tga:        stdPostmarketFlow('TGA PV Responsibilities / RMP', 'TGA eBS portal'),
    pmda: [
      { t:'q', text:'<b>From a Japan GPSP study?</b>' },
      { t:'y', text:'Yes \u2192 GPSP Ordinance + PFAS apply' },
      { t:'q', text:'<b>ADR/SAE serious + unexpected?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> PMDA' },
      { t:'y', text:'Serious expected \u2192 <b>30 days</b> PMDA' },
      { t:'n', text:'Non-serious \u2192 Study periodic report' },
      { t:'i', text:'GPSP re-examination period: 4-10 years. PMDA quarterly/annual aggregate.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day PMDA', detail:'PFAS / GPSP Ordinance' },
        { cls:'out-conditional',title:'Serious expected \u2192 30-day PMDA',    detail:'GPSP post-market specific' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Periodic',            detail:'PMDA aggregate' }
      ]}
    ],
    mfds:       stdPostmarketFlow('KGVP PMSS / re-exam obligations', 'MFDS'),
    sfda:       stdPostmarketFlow('Saudi GVP + PMS conditions', 'SFDA portal'),
    swissmedic: stdPostmarketFlow('Swiss GVP Module VIII (PASS)', 'Swissmedic portal', true),
    anvisa:     stdPostmarketFlow('RDC 204/2017 PVMS', 'ANVISA Notivisa'),
    cdsco: [
      { t:'q', text:'<b>From India Schedule Y Phase IV / PMSS?</b>' },
      { t:'y', text:'Yes \u2192 Schedule Y Phase IV obligations + PvPI' },
      { t:'q', text:'<b>SAE serious + unexpected?</b>' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> CDSCO/PvPI' },
      { t:'y', text:'Expected fatal \u2192 <b>15 days</b>' },
      { t:'n', text:'Non-serious \u2192 Annual' },
      { t:'i', text:'Phase IV mandatory for new drugs (4 years). Sugam/Vigiflow. English.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day CDSCO/PvPI', detail:'Schedule Y Phase IV' },
        { cls:'out-conditional',title:'Serious expected fatal \u2192 15-day',         detail:'PvPI guidance' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Annual report',             detail:'Schedule Y' }
      ]}
    ],
    nmpa: [
      { t:'q', text:'<b>From China Phase IV / PMSS?</b>' },
      { t:'y', text:'Yes \u2192 NMPA ADR Measures 2011/2022 + Phase IV' },
      { t:'q', text:'<b>Is ADR serious?</b>' },
      { t:'y', text:'Serious \u2192 <b>15 days</b> CNKI' },
      { t:'y', text:'Non-serious \u2192 <b>30 days</b> CNKI' },
      { t:'i', text:'Phase IV 5-year commitment. Chinese narrative.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious \u2192 15-day CNKI',     detail:'NMPA Phase IV' },
        { cls:'out-report',  title:'Non-serious \u2192 30-day CNKI',  detail:'All ADRs reportable' },
        { cls:'out-noreport',title:'< 4 criteria \u2192 Log only',     detail:'Document' }
      ]}
    ],
    tfda:    stdPostmarketFlow('TFDA Phase IV / ADR regulations', 'TFDA portal'),
    moh:     stdPostmarketFlow('Israel MOH Phase IV / GVP', 'MOH PV department'),
    medsafe: stdPostmarketFlow('Medicines Act / consent conditions', 'Medsafe portal'),
    nafdac:  stdPostmarketFlow('NAFDAC PV / Phase IV commitment', 'NAFDAC PV directorate')
  };
}

function stdPostmarketFlow(framework, portal, withNonSerious) {
  const flow = [
    { t:'q', text:'<b>From a post-market surveillance study / RMP in this jurisdiction?</b>' },
    { t:'y', text:'Yes \u2192 ' + framework + ' applies' },
    { t:'q', text:'<b>SAE serious + unexpected?</b>' },
    { t:'y', text:'Yes \u2192 <b>15 days</b> to ' + portal }
  ];
  if (withNonSerious) flow.push({ t:'y', text:'Non-serious \u2192 <b>90 days</b>' });
  flow.push({ t:'n', text:'Non-serious / expected \u2192 PSUR; no expedited' });
  flow.push({ t:'i', text:'Post-market study commitments often condition of registration.' });
  const outcomes = [{ cls:'out-report', title:'Serious unexpected \u2192 15-day ' + portal, detail:framework }];
  if (withNonSerious) outcomes.push({ cls:'out-conditional', title:'Non-serious \u2192 90-day', detail:'Post-market study ADR' });
  outcomes.push({ cls:'out-noreport', title:'Non-serious / expected \u2192 PSUR', detail:'Periodic' });
  flow.push({ outcomes:outcomes });
  return flow;
}

function buildSolicitedFlows() {
  return {
    fda: [
      { t:'q', text:'<b>From a Patient Support Program (PSP), market research, or DMP?</b>' },
      { t:'y', text:'Yes \u2192 FDA 2011 Guidance + 21 CFR 312.32/314.80' },
      { t:'q', text:'<b>MAH-controlled program?</b>' },
      { t:'y', text:'MAH-controlled \u2192 Treated as spontaneous if no study protocol' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> MedWatch' },
      { t:'n', text:'Independent program \u2192 Depends on MAH "received" status' },
      { t:'i', text:'PSP AEs treated as company-received. 4 minimum criteria apply.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected (MAH-controlled) \u2192 15-day', detail:'21 CFR 314.80 / FDA PSP guidance' },
        { cls:'out-conditional',title:'Serious expected \u2192 PADER periodic',             detail:'Periodic reporting' },
        { cls:'out-noreport',   title:'Non-serious \u2192 PADER only',                      detail:'No expedited' }
      ]}
    ],
    ema: [
      { t:'q', text:'<b>EU MAH-sponsored PSP or observational program?</b>' },
      { t:'y', text:'Yes \u2192 GVP Module VI \u00a7VI.B.1.3 (solicited sources)' },
      { t:'q', text:'<b>Individual report vs organized study?</b>' },
      { t:'y', text:'Solicited individual \u2192 Treated as spontaneous' },
      { t:'y', text:'Serious unexpected \u2192 <b>15 days</b> EudraVigilance' },
      { t:'n', text:'Organized study \u2192 Follow NIPASS rules (GVP Module VIII)' },
      { t:'i', text:'PSP AEs must be reported if meeting spontaneous ICSR criteria.' },
      { outcomes:[
        { cls:'out-report',     title:'Solicited serious unexpected \u2192 15-day', detail:'GVP Module VI \u00a7VI.B.1.3' },
        { cls:'out-conditional',title:'Organized data collection \u2192 NIPASS',     detail:'GVP Module VIII' },
        { cls:'out-noreport',   title:'Non-serious \u2192 90-day',                   detail:'Treated as spontaneous' }
      ]}
    ],
    mhra:       stdSolicitedFlow('UK GVP VI solicited source', 'MHRA Yellow Card'),
    hc:         stdSolicitedFlow('FDR C.01.016 / MHPD guidance', 'Health Canada MedEffect'),
    tga:        stdSolicitedFlow('TGA PV guidance / solicited', 'TGA eBS'),
    pmda: [
      { t:'q', text:'<b>From Japan MAH-sponsored DIC or patient program?</b>' },
      { t:'y', text:'Yes \u2192 PFAS solicited source provisions' },
      { t:'q', text:'<b>Serious + unexpected?</b>' },
      { t:'y', text:'Yes \u2192 <b>15 days</b> PMDA' },
      { t:'y', text:'Serious expected \u2192 <b>30 days</b>' },
      { t:'n', text:'Non-serious \u2192 Periodic' },
      { t:'i', text:'Drug information centers commonly used. Japanese narrative required.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day PMDA',    detail:'PFAS / solicited source' },
        { cls:'out-conditional',title:'Serious expected \u2192 30-day PMDA',       detail:'Expected ADR' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Periodic',                detail:'Aggregate' }
      ]}
    ],
    mfds:       stdSolicitedFlow('KGVP solicited source', 'MFDS'),
    sfda:       stdSolicitedFlow('Saudi GVP solicited source', 'SFDA PV portal'),
    swissmedic: stdSolicitedFlow('Swiss GVP solicited source', 'Swissmedic portal'),
    anvisa:     stdSolicitedFlow('RDC 204/2017 solicited source', 'ANVISA Notivisa'),
    cdsco:      stdSolicitedFlow('Schedule Y / PvPI solicited source', 'CDSCO/PvPI Vigiflow'),
    nmpa: [
      { t:'q', text:'<b>From China MAH-sponsored PSP / DMP?</b>' },
      { t:'y', text:'Yes \u2192 NMPA ADR Measures: all ADRs reportable' },
      { t:'q', text:'<b>Is SAE serious?</b>' },
      { t:'y', text:'Serious \u2192 <b>15 days</b> CNKI' },
      { t:'y', text:'Non-serious \u2192 <b>30 days</b> CNKI' },
      { t:'n', text:'< 4 criteria \u2192 Document' },
      { t:'i', text:'China: no solicited/spontaneous distinction; all ADRs reportable.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious \u2192 15-day CNKI',     detail:'NMPA ADR Measures' },
        { cls:'out-report',  title:'Non-serious \u2192 30-day CNKI',  detail:'All ADRs reportable' },
        { cls:'out-noreport',title:'< 4 criteria \u2192 Log only',     detail:'Document' }
      ]}
    ],
    tfda:    stdSolicitedFlow('TFDA ADR regulations / solicited', 'TFDA portal'),
    moh:     stdSolicitedFlow('Israel MOH GVP / solicited source', 'MOH PV department'),
    medsafe: stdSolicitedFlow('Medsafe PV guidance / solicited', 'Medsafe portal'),
    nafdac:  stdSolicitedFlow('NAFDAC PV / solicited', 'NAFDAC PV directorate')
  };
}

function stdSolicitedFlow(framework, portal) {
  return [
    { t:'q', text:'<b>From MAH-sponsored patient support program?</b>' },
    { t:'y', text:'Yes \u2192 ' + framework + ' applies; treated as company-received' },
    { t:'q', text:'<b>Is SAE serious + unexpected?</b>' },
    { t:'y', text:'Yes \u2192 <b>15 days</b> to ' + portal },
    { t:'n', text:'Non-serious \u2192 Annual PSUR; no expedited' },
    { t:'i', text:'Solicited AEs from MAH programs treated same as spontaneous reports.' },
    { outcomes:[
      { cls:'out-report',  title:'Serious unexpected \u2192 15-day ' + portal, detail:framework },
      { cls:'out-noreport',title:'Non-serious \u2192 Annual PSUR',              detail:'Periodic' }
    ]}
  ];
}

function buildDigitalFlows() {
  return {
    fda: [
      { t:'q', text:'<b>From MAH-owned digital channel (website, app, social media)?</b>' },
      { t:'y', text:'Yes \u2192 FDA 2013 Social Media Guidance + 21 CFR 314.80' },
      { t:'q', text:'<b>4 minimum ICSR criteria exist?</b>' },
      { t:'y', text:'4 criteria + serious + unexpected \u2192 <b>15 days</b> MedWatch' },
      { t:'y', text:'4 criteria + non-serious/expected \u2192 PADER periodic' },
      { t:'n', text:'< 4 criteria \u2192 Document monitoring; no ICSR' },
      { t:'i', text:'Third-party social media monitoring not required. Company-owned channels mandatory.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected (4 criteria) \u2192 15-day', detail:'21 CFR 314.80 / FDA social media guidance' },
        { cls:'out-conditional',title:'Non-serious / expected \u2192 PADER',           detail:'Periodic' },
        { cls:'out-noreport',   title:'< 4 criteria \u2192 Monitoring log',             detail:'Document required' }
      ]}
    ],
    ema:        stdDigitalFlow('GVP Module VI \u00a7VI.B.1.3', 'EudraVigilance', true),
    mhra:       stdDigitalFlow('UK GVP Module VI / digital', 'Yellow Card', true),
    hc:         stdDigitalFlow('FDR C.01.016 / digital source', 'Health Canada MedEffect'),
    tga:        stdDigitalFlow('TGA PV guidance / digital', 'TGA eBS'),
    pmda: [
      { t:'q', text:'<b>From Japan MAH-owned app/website/MR inquiry?</b>' },
      { t:'y', text:'Yes \u2192 PFAS: digital AEs are company-received' },
      { t:'q', text:'<b>4 criteria + serious + unexpected?</b>' },
      { t:'y', text:'Yes \u2192 <b>15 days</b> PMDA' },
      { t:'y', text:'Serious expected \u2192 <b>30 days</b>' },
      { t:'n', text:'Non-serious / < 4 criteria \u2192 Periodic' },
      { t:'i', text:'Company-owned digital channels = company-received. Japanese narrative.' },
      { outcomes:[
        { cls:'out-report',     title:'Serious unexpected \u2192 15-day PMDA',    detail:'PFAS / digital source' },
        { cls:'out-conditional',title:'Serious expected \u2192 30-day PMDA',       detail:'Expected ADR' },
        { cls:'out-noreport',   title:'Non-serious \u2192 Periodic',                detail:'Aggregate' }
      ]}
    ],
    mfds:       stdDigitalFlow('KGVP / digital source', 'MFDS'),
    sfda:       stdDigitalFlow('Saudi GVP / digital', 'SFDA portal'),
    swissmedic: stdDigitalFlow('Swiss GVP / digital', 'Swissmedic portal', true),
    anvisa:     stdDigitalFlow('RDC 204/2017 / digital', 'ANVISA Notivisa'),
    cdsco:      stdDigitalFlow('Schedule Y / digital source', 'CDSCO/PvPI Vigiflow'),
    nmpa: [
      { t:'q', text:'<b>From China MAH-owned digital channel?</b>' },
      { t:'y', text:'Yes \u2192 NMPA ADR Measures: all digital ADRs reportable' },
      { t:'q', text:'<b>4 criteria met?</b>' },
      { t:'y', text:'Serious \u2192 <b>15 days</b> CNKI' },
      { t:'y', text:'Non-serious \u2192 <b>30 days</b> CNKI' },
      { t:'n', text:'< 4 criteria \u2192 Document' },
      { t:'i', text:'All ADRs reportable regardless of source/expectedness.' },
      { outcomes:[
        { cls:'out-report',  title:'Serious \u2192 15-day CNKI',     detail:'NMPA / digital' },
        { cls:'out-report',  title:'Non-serious \u2192 30-day CNKI',  detail:'All ADRs reportable' },
        { cls:'out-noreport',title:'< 4 criteria \u2192 Log',          detail:'Document' }
      ]}
    ],
    tfda:    stdDigitalFlow('TFDA ADR / digital', 'TFDA'),
    moh:     stdDigitalFlow('Israel MOH GVP / digital', 'MOH'),
    medsafe: stdDigitalFlow('Medsafe / digital source', 'Medsafe portal'),
    nafdac:  stdDigitalFlow('NAFDAC PV / digital source', 'NAFDAC')
  };
}

function stdDigitalFlow(framework, portal, withNonSerious) {
  const flow = [
    { t:'q', text:'<b>From MAH-owned digital platform (app, website, social media)?</b>' },
    { t:'y', text:'Yes \u2192 ' + framework + ' applies' },
    { t:'q', text:'<b>4 minimum criteria + serious + unexpected?</b>' },
    { t:'y', text:'Yes \u2192 <b>15 days</b> to ' + portal }
  ];
  if (withNonSerious) flow.push({ t:'y', text:'Non-serious \u2192 <b>90 days</b>' });
  flow.push({ t:'n', text:'< 4 criteria \u2192 Document; no ICSR' });
  flow.push({ t:'i', text:'Digital channel AEs = company-received spontaneous reports.' });
  const outcomes = [{ cls:'out-report', title:'Serious unexpected \u2192 15-day ' + portal, detail:framework }];
  if (withNonSerious) outcomes.push({ cls:'out-conditional', title:'Non-serious \u2192 90-day', detail:'Digital ICSR' });
  outcomes.push({ cls:'out-noreport', title:'< 4 criteria \u2192 Document only', detail:'No ICSR' });
  flow.push({ outcomes:outcomes });
  return flow;
}

function buildAggregateFlows() {
  return {
    fda: [
      { t:'i', text:'<b>PADER</b>: marketed drugs (NDA/ANDA) — quarterly x3 yrs, then annual.' },
      { t:'i', text:'<b>PBRER</b>: biologic license holders (BLA).' },
      { t:'i', text:'<b>DSUR</b>: clinical trial annual safety report.' },
      { t:'i', text:'No expedited ICSR for aggregate types — cumulative summaries.' },
      { outcomes:[
        { cls:'out-conditional',title:'Marketed drug \u2192 PADER',          detail:'21 CFR 314.81(b)(2)' },
        { cls:'out-conditional',title:'Biologic \u2192 PBRER annual',        detail:'21 CFR 600.80 / ICH E2C(R2)' },
        { cls:'out-conditional',title:'IND \u2192 DSUR annual',              detail:'21 CFR 312.33 / ICH E2F' },
        { cls:'out-noreport',   title:'No expedited ICSR for aggregate',     detail:'Cumulative summary only' }
      ]}
    ],
    ema:        aggFlow('PBRER per EURD list', 'GVP Module VII / ICH E2C(R2)'),
    mhra:       aggFlow('PSUR/PBRER per MHRA schedule', 'UK GVP Module VII'),
    hc:         aggFlow('PSUR/PBRER annual', 'FDR / MHPD PSUR guidance'),
    tga:        aggFlow('PSUR per ARTG condition', 'TGA PSUR guidance / ICH E2C(R2)'),
    pmda: [
      { t:'i', text:'<b>PSUR</b>: per IYRS. Semi-annual for first 2 years, then annual. Japan-specific addendum.' },
      { t:'i', text:'<b>Re-examination period reports</b> required (GPSP Ordinance).' },
      { t:'i', text:'<b>DSUR</b>: CT annual.' },
      { outcomes:[
        { cls:'out-conditional',title:'Japan drug \u2192 PSUR per IYRS',            detail:'PFAS / PMDA PSUR guidance' },
        { cls:'out-conditional',title:'Re-examination \u2192 Periodic re-exam report', detail:'GPSP Ordinance' },
        { cls:'out-conditional',title:'CT \u2192 DSUR annual',                       detail:'PFAS CT obligations' },
        { cls:'out-noreport',   title:'No expedited ICSR for aggregate',            detail:'Cumulative summary' }
      ]}
    ],
    mfds:       aggFlow('PSUR semi-annual then annual', 'KGVP PSUR schedule'),
    sfda:       aggFlow('PSUR annual', 'SFDA GVP / ICH E2C(R2)'),
    swissmedic: aggFlow('PBRER (EU-aligned)', 'Swiss HMG / ICH E2C(R2)'),
    anvisa:     aggFlow('PSUR annual (Portuguese)', 'RDC 204/2017 / ICH E2C(R2)'),
    cdsco: [
      { t:'i', text:'<b>PSUR</b>: per Schedule Y IBD timetable. Quarterly x2, semi-annual x2, then annual.' },
      { t:'i', text:'<b>Phase IV annual safety reports</b> required.' },
      { t:'i', text:'English. Both domestic and global data.' },
      { outcomes:[
        { cls:'out-conditional',title:'India drug \u2192 PSUR per Schedule Y',  detail:'Schedule Y / ND&CT Rules 2019' },
        { cls:'out-conditional',title:'Phase IV \u2192 Annual safety report',     detail:'Schedule Y Phase IV' },
        { cls:'out-noreport',   title:'No expedited ICSR for aggregate',         detail:'Cumulative summary' }
      ]}
    ],
    nmpa: [
      { t:'i', text:'<b>PSUR</b>: China-specific. Annual post-approval. Chinese language required.' },
      { t:'i', text:'All ADRs included in PSUR — no expected exclusion.' },
      { outcomes:[
        { cls:'out-conditional',title:'NMPA approved \u2192 PSUR annual (Chinese)',          detail:'NMPA ADR Measures / regulations' },
        { cls:'out-noreport',   title:'No expedited ICSR for aggregate (individual reporting parallel)', detail:'Parallel reporting required' }
      ]}
    ],
    tfda:    aggFlow('PSUR annual', 'TFDA regulations / ICH E2C(R2)'),
    moh:     aggFlow('PSUR annual (English/Hebrew)', 'Israel MOH GVP / ICH E2C(R2)'),
    medsafe: aggFlow('PSUR annual', 'Medicines Act / Medsafe guidance'),
    nafdac:  aggFlow('PSUR annual', 'NAFDAC PV regulations')
  };
}

function aggFlow(title, detail) {
  return [
    { t:'i', text:'Periodic aggregate reports apply per ' + detail + '.' },
    { t:'i', text:'No expedited individual ICSR for aggregate submissions \u2014 cumulative summaries only.' },
    { outcomes:[
      { cls:'out-conditional',title:title,                                  detail:detail },
      { cls:'out-conditional',title:'CT \u2192 DSUR annual',                detail:'Per jurisdiction CT regs' },
      { cls:'out-noreport',   title:'No expedited ICSR for aggregate',     detail:'Periodic summary only' }
    ]}
  ];
}

/* ─── STATE + RENDER ─────────────────────────────────────────── */
let repState = { source:null, ha:null };

function renderReportabilityScreen() {
  const container = document.getElementById('screen-reportability');
  if (!container) {
    console.error('[Reportability] container #screen-reportability not found');
    return;
  }
  repState = { source:null, ha:null };
  renderRepHome(container);
}

function renderRepHome(container) {
  let h = '';
  h += '<div class="rep-breadcrumb">';
  h += '<span class="rep-bc-active">All sources</span>';
  h += '</div>';
  h += '<div class="rep-panel-title">ICSR reportability decision tree</div>';
  h += '<div class="rep-panel-sub">Select the source/origin of the adverse event report to drill down.</div>';
  h += '<div class="rep-grid rep-grid-2">';
  REP_SOURCES.forEach(function(s) {
    h += '<div class="rep-card" onclick="repSelectSource(\'' + s.id + '\')">';
    h += '<div class="rep-card-icon"><i class="fas ' + s.icon + '"></i></div>';
    h += '<div class="rep-card-label">' + s.label + '</div>';
    h += '<div class="rep-card-sub">' + s.sub + '</div>';
    h += '</div>';
  });
  h += '</div>';
  container.innerHTML = h;
}

function renderRepHAs(container) {
  const s = REP_SOURCES.find(function(x) { return x.id === repState.source; });
  let h = '';
  h += '<div class="rep-breadcrumb">';
  h += '<span class="rep-bc-link" onclick="repGoHome()">All sources</span> ';
  h += '<span class="rep-bc-sep">&rsaquo;</span> ';
  h += '<span class="rep-bc-active">' + s.label + '</span>';
  h += '</div>';
  h += '<div class="rep-panel-title">' + s.label + ' &mdash; select health authority</div>';
  h += '<div class="rep-panel-sub">Which regulatory authority are you assessing reportability for?</div>';
  h += '<div class="rep-grid rep-grid-3">';
  REP_HAS.forEach(function(ha) {
    const hasFlow = REP_FLOWS[repState.source] && REP_FLOWS[repState.source][ha.id];
    const style = hasFlow ? '' : 'opacity:.4;pointer-events:none;';
    h += '<div class="rep-card" style="' + style + '" onclick="repSelectHA(\'' + ha.id + '\')">';
    h += '<div class="rep-ha-region">' + ha.region + '</div>';
    h += '<div class="rep-card-label">' + ha.label + '</div>';
    h += '</div>';
  });
  h += '</div>';
  container.innerHTML = h;
}

function renderRepFlow(container) {
  const s = REP_SOURCES.find(function(x) { return x.id === repState.source; });
  const ha = REP_HAS.find(function(x) { return x.id === repState.ha; });
  const flow = REP_FLOWS[repState.source][repState.ha];

  let h = '';
  h += '<div class="rep-breadcrumb">';
  h += '<span class="rep-bc-link" onclick="repGoHome()">All sources</span> ';
  h += '<span class="rep-bc-sep">&rsaquo;</span> ';
  h += '<span class="rep-bc-link" onclick="repGoSource()">' + s.label + '</span> ';
  h += '<span class="rep-bc-sep">&rsaquo;</span> ';
  h += '<span class="rep-bc-active">' + ha.label + '</span>';
  h += '</div>';
  h += '<div class="rep-panel-title">' + s.label + ' &rarr; ' + ha.label + '</div>';
  h += '<div class="rep-panel-sub">Reportability decision flow for this ICSR source &times; HA combination.</div>';
  h += '<div class="rep-flow-wrap">';

  flow.forEach(function(step) {
    if (step.outcomes) {
      h += '<hr class="rep-section-divider">';
      step.outcomes.forEach(function(o) {
        h += '<div class="rep-outcome-box ' + o.cls + '">';
        h += '<div class="rep-out-text">' + o.title + '</div>';
        if (o.detail) h += '<div class="rep-out-detail">' + o.detail + '</div>';
        h += '</div>';
      });
    } else {
      const cls = step.t === 'q' ? 'rep-step-q' :
                  step.t === 'y' ? 'rep-step-y' :
                  step.t === 'n' ? 'rep-step-n' :
                  step.t === 'i' ? 'rep-step-i' : 'rep-step-g';
      const lbl = step.t === 'q' ? '?' :
                  step.t === 'y' ? 'Y' :
                  step.t === 'n' ? 'N' :
                  step.t === 'i' ? 'i' : '&middot;';
      h += '<div class="rep-flow-step">';
      h += '<div class="rep-step-node ' + cls + '">' + lbl + '</div>';
      h += '<div class="rep-step-text">' + step.text + '</div>';
      h += '</div>';
    }
  });

  h += '</div>';
  container.innerHTML = h;
}

function repSelectSource(id) {
  repState.source = id;
  repState.ha = null;
  renderRepHAs(document.getElementById('screen-reportability'));
}

function repSelectHA(id) {
  repState.ha = id;
  renderRepFlow(document.getElementById('screen-reportability'));
}

function repGoHome() {
  repState = { source:null, ha:null };
  renderRepHome(document.getElementById('screen-reportability'));
}

function repGoSource() {
  repState.ha = null;
  renderRepHAs(document.getElementById('screen-reportability'));
}

// Expose globally for inline onclick handlers
window.renderReportabilityScreen = renderReportabilityScreen;
window.repSelectSource = repSelectSource;
window.repSelectHA = repSelectHA;
window.repGoHome = repGoHome;
window.repGoSource = repGoSource;
