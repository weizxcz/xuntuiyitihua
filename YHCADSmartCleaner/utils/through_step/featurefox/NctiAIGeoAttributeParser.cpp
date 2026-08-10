#include "NctiAIGeoAttributeParser.h"
#include "NctiDocElementPubFun.h"
#include "NctiDocViewManager.h"
#include "NctiAiModelSystemObject.h"
#include "NctiHistoryManager.h"
#include "NctiDisplayModelBody.h"
#include "NctiBaseModel.h"
#include "NctiDisplayDocCustomContainer.h"
#include "NctiGeometryFunction.h"
#include "NctiDocument.h"
#include "json.h"
#include <fstream>

using namespace NCTI;
std::pair<std::string, std::string> NctiAIGeoAttributeParser::m_pairRevceObjName;
std::map<std::string, StretFaceAttributes> NctiAIGeoAttributeParser::m_mapFaceAttributes;
Ncti_Boolean NCTI::NctiAIGeoAttributeParser::GetGeoAttributes(const std::string& i_jsonPath, GeometryAttributes& geoAttr)
{
	std::ifstream ifs(i_jsonPath);
	if (!ifs.is_open()) {
		//Failed to open file.
		return false;
	}

	Json::Value root;
	Json::CharReaderBuilder readerBuilder;
	std::string errs;
	if (!Json::parseFromStream(readerBuilder, ifs, &root, &errs)) {
		//"Failed to parse JSON.
		return false;
	}

	Json::Value face = root["face_attributes"];
	if (face.type() == Json::arrayValue)
	{
		for (const auto& item : face) {
			geoAttr.face_attributes.push_back(item.asString());
		}
	}

	Json::Value edge = root["edge_attributes"];
	if (edge.type() == Json::arrayValue)
	{
		for (const auto& item : edge) {
			geoAttr.edge_attributes.push_back(item.asString());
		}
	}

	Json::Value uvGrid = root["UV-grid"];
	if (uvGrid.type() == Json::objectValue)
	{
		geoAttr.uvGrid.num_srf_u = uvGrid["num_srf_u"].asInt();
		geoAttr.uvGrid.num_srf_v = uvGrid["num_srf_v"].asInt();
		geoAttr.uvGrid.num_crv_u = uvGrid["num_crv_u"].asInt();
	}

	//释放资源
	ifs.close();
	return true;
}

Ncti_Boolean NctiAIGeoAttributeParser::ImportAiResultToSys(
	NctiDocument* i_pDocment,
	const char* i_ObjName,
	const std::vector<std::string>& i_ResultNameVec,
	const std::vector<std::vector<Ncti_Long>>& i_ResultFaceVecVec,
	const std::vector<std::vector<Ncti_Long>>& i_ResultBottomFaceVecVec)
{
	NctiDisplayObject* pObj = nullptr;
	NctiDocElementPubFun::GetObjectListByName(i_pDocment, NctiDisplayModelBody::ID, i_ObjName, pObj);

	NctiDocViewManager* pDocView = NctiDocViewManager::GetDocViewManager(i_pDocment->GetBaseModel());
	NctiHistoryManager* pHisMan = NctiHistoryManager::GetHistoryManager(i_pDocment->GetBaseModel());
	if (pHisMan->GetActive())
	{
		int iDepth = 0;
		pHisMan->StartState("ImportAiResultToSys", iDepth);
	}
	NctiAiModelSystemObject* pAiModelSystemObject = NctiDocElementPubFun::GetAiModelSystemObject(i_pDocment->GetBaseModel());
	
	NCTI_API_BEGIN(pHisMan)
	if (pObj && pAiModelSystemObject)
	{
		NctiDisplayModelBody* pModelBody = (NctiDisplayModelBody*)pObj;
		NctiDisplayDocCustomContainer* pCusDoc = (NctiDisplayDocCustomContainer*)pModelBody->GetDocContainer();

		for (Ncti_Size i = 0; i < i_ResultNameVec.size(); i++)
		{
			std::vector<AiModelData> aiModelDatas;
			for (Ncti_Size ii = 0; ii < i_ResultFaceVecVec[i].size(); ii++)
			{
				AiModelData modeldata;
				modeldata.ObjName = i_ObjName;
				modeldata.type = 1;
				NCTI_MODEL_TAG ModelFace = nullptr;
				const Ncti_Long curFace = i_ResultFaceVecVec[i][ii];
				pCusDoc->get_void_from_tag(pModelBody, ModelFace, curFace);
				// 3 个 UV 采样槽位（中心 / (0,0) / (1,1)），由 get_point_on_face_by_uv 覆写
				modeldata.pts.resize(3);
				NctiGeometryResult bres1 = NctiGeometryFunction::get_point_on_face_by_uv(pCusDoc, pModelBody->GetNctiBody(), ModelFace, 0.5, 0.5, modeldata.pts[0]);
				NctiGeometryResult bres2 = NctiGeometryFunction::get_point_on_face_by_uv(pCusDoc, pModelBody->GetNctiBody(), ModelFace, 0.0, 0.0, modeldata.pts[1]);
				NctiGeometryResult bres3 = NctiGeometryFunction::get_point_on_face_by_uv(pCusDoc, pModelBody->GetNctiBody(), ModelFace, 1.0, 1.0, modeldata.pts[2]);
				// 判断当前面是否在底面集合中（原代码用同名 ii 遮蔽，仅做按位置配对；改为值查找）
				modeldata.faceType = 0;
				for (Ncti_Long bottom : i_ResultBottomFaceVecVec[i])
				{
					if (curFace == bottom)
					{
						modeldata.faceType = 1;
						break;
					}
				}

				aiModelDatas.push_back(modeldata);
			}
			pAiModelSystemObject->AddLable(i_ResultNameVec[i], aiModelDatas);
		}
	}

	NCTI_API_END
		if (pHisMan != nullptr && pHisMan->GetActive())
		{
			int iDepth = 0;
			pHisMan->NoteState(NCTI_SUCCEEDED, iDepth);
		}
	return true;
}

void NCTI::NctiAIGeoAttributeParser::GetStretFaceAttributes(const std::string& objName, StretFaceAttributes& faceAttributes)
{
	auto iter = m_mapFaceAttributes.find(objName);
	if (iter != m_mapFaceAttributes.end())
	{
		faceAttributes = iter->second;
	}
}
