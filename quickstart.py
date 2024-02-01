import os
import azure.ai.vision as sdk
from dotenv import load_dotenv

load_dotenv()

service_options = sdk.VisionServiceOptions(os.environ["VISION_ENDPOINT"],
                                           os.environ["VISION_KEY"])

analysis_options = sdk.ImageAnalysisOptions()

analysis_options.features = (
    sdk.ImageAnalysisFeature.CAPTION |
    sdk.ImageAnalysisFeature.TEXT
)

analysis_options.language = "en"
analysis_options.gender_neutral_caption = True

def AIsolve(img_urls):
    """Analyzes the provided image URLs and returns their captions."""
    captions = []

    for img_url in img_urls:
        vision_source = sdk.VisionSource(url=img_url)
        image_analyzer = sdk.ImageAnalyzer(service_options, vision_source, analysis_options)

        result = image_analyzer.analyze()

        if result.reason == sdk.ImageAnalysisResultReason.ANALYZED:
            if result.caption is not None:
                captions.append(result.caption.content)
        else:
            error_details = sdk.ImageAnalysisErrorDetails.from_result(result)
            print(" Analysis failed for URL:", img_url)
            print("   Error reason: {}".format(error_details.reason))
            print("   Error code: {}".format(error_details.error_code))
            print("   Error message: {}".format(error_details.message))
    
    return captions



